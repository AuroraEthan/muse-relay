"""Authenticated JSON queue; Railway terminates public HTTPS."""
import hmac
import json
import os
import re
import sqlite3
import uuid
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from queue_store import Conflict, Queue
from muse_store import Registry, ServiceError
import muse_api

MAX_BODY = 262144
ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
STATIC = Path(__file__).parent / 'static'
ASSETS = {'/': ('muse.html', 'text/html; charset=utf-8'),
          '/legacy': ('index.html', 'text/html; charset=utf-8'),
          '/muse-test.js': ('muse-test.js', 'text/javascript; charset=utf-8'),
          '/muse.js': ('muse.js', 'text/javascript; charset=utf-8'),
          '/muse.css': ('muse.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/app.css': ('app.css', 'text/css; charset=utf-8'),
          '/api-docs': ('api-docs.html', 'text/html; charset=utf-8'),
          '/openapi.json': ('openapi.json', 'application/json; charset=utf-8')}


class BadRequest(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, fmt, *args):
        # Avoid logging paths, credentials and payloads.
        print(f'{self.command} response', flush=True)

    def reply(self, status, value, headers=None):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.reply_bytes(status, body, 'application/json; charset=utf-8', headers)

    def reply_bytes(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        if (self.server.public_send and urlsplit(self.path).path == '/send') or muse_api.SEND_PATH.fullmatch(urlsplit(self.path).path):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Idempotency-Key, Authorization')
            self.send_header('Access-Control-Max-Age', '600')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def session_token(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie['relay_session'].value if 'relay_session' in cookie else ''
            return token if re.fullmatch(r'[A-Za-z0-9_-]{43}', token) else ''
        except CookieError:
            return ''

    def request_origin(self):
        return self.server.public_origin or 'http://' + self.headers.get('Host', '')

    def session_cookie(self, token, max_age):
        secure = '; Secure' if self.request_origin().startswith('https://') else ''
        return f'relay_session={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}'

    def auth(self, role):
        expected = 'Bearer ' + self.server.tokens[role]
        actual = self.headers.get('Authorization', '')
        if hmac.compare_digest(expected.encode(), actual.encode()):
            return
        if role == 'producer' and self.server.queue.valid_session(self.session_token(), self.server.tokens['producer']):
            if self.command not in ('GET', 'HEAD') and self.headers.get('Origin') != self.request_origin():
                raise BadRequest(403, 'same_origin_required')
            return
        raise BadRequest(401, 'unauthorized')

    def read_body(self):
        if self.headers.get('Transfer-Encoding'):
            raise BadRequest(400, 'chunked_body_not_supported')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise BadRequest(400, 'invalid_content_length')
        if size < 0 or size > MAX_BODY:
            raise BadRequest(413, 'max_body_262144_bytes')
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise BadRequest(400, 'incomplete_body')
        return raw

    def read_json(self):
        try:
            raw = self.read_body()
            def reject_constant(value):
                raise ValueError('non_finite_json_number')
            value = json.loads(raw, parse_constant=reject_constant)
            # Validate numerical overflow and nesting before passing to storage.
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (ValueError, UnicodeError, RecursionError):
            raise BadRequest(400, 'invalid_json')
        if not isinstance(value, dict):
            raise BadRequest(400, 'expected_json_object')
        return value

    def dispatch(self):
        path = urlsplit(self.path).path
        if muse_api.dispatch(self):
            return
        if path == '/config' and self.command == 'GET':
            return self.reply(200, dict(public_send=self.server.public_send, max_message_bytes=MAX_BODY))
        if path == '/send' and self.command == 'OPTIONS' and self.server.public_send:
            return self.reply_bytes(204, b'', 'text/plain; charset=utf-8')
        if path == '/session' and self.command == 'GET':
            self.auth('producer')
            return self.reply(200, dict(authenticated=True))
        if path == '/session' and self.command == 'POST':
            self.auth('producer')
            self.read_body()
            token = self.server.queue.issue_session(self.server.tokens['producer'])
            return self.reply(200, dict(authenticated=True),
                              {'Set-Cookie': self.session_cookie(token, 2592000)})
        if path == '/logout' and self.command == 'POST':
            self.auth('producer')
            self.read_body()
            self.server.queue.revoke_session(self.session_token())
            return self.reply(200, dict(ok=True), {'Set-Cookie': self.session_cookie('', 0)})
        if re.fullmatch(r'/m/m_[a-f0-9]{32}/?', path) and self.command in ('GET', 'HEAD'):
            return self.reply_bytes(200, (STATIC / 'muse.html').read_bytes(), 'text/html; charset=utf-8')
        if path in ASSETS and self.command in ('GET', 'HEAD'):
            name, content_type = ASSETS[path]
            return self.reply_bytes(200, (STATIC / name).read_bytes(), content_type)
        if path == '/health' and self.command in ('GET', 'HEAD'):
            return self.reply(200, dict(ok=True, service='vm-connectivity-check',
                              time=datetime.now(timezone.utc).isoformat()))
        if self.command == 'POST' and path == '/send':
            if not self.server.public_send:
                self.auth('producer')
            if self.headers.get_content_type() != 'text/plain' or self.headers.get_content_charset('utf-8') not in ('utf-8', 'utf8'):
                raise BadRequest(415, 'expected_utf8_text_plain')
            try:
                text = self.read_body().decode('utf-8')
            except UnicodeError:
                raise BadRequest(400, 'invalid_utf8')
            if not text.strip():
                raise BadRequest(400, 'message_text_required')
            if len(json.dumps({'message': text}, ensure_ascii=False).encode()) > MAX_BODY:
                raise BadRequest(413, 'encoded_message_exceeds_262144_bytes')
            request_key = self.headers.get('Idempotency-Key')
            if request_key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', request_key):
                raise BadRequest(400, 'invalid_retry_key')
            ident, created = self.server.queue.put_text(text, request_key)
            return self.reply(201 if created else 200, dict(id=ident, created=created))
        if self.command == 'GET' and path == '/messages':
            self.auth('producer')
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            try:
                limit = int(query.get('limit', ['25'])[0])
                before = int(query['before'][0]) if 'before' in query else None
                if not 1 <= limit <= 100 or (before is not None and not 1 <= before <= 9223372036854775807):
                    raise ValueError()
            except ValueError:
                raise BadRequest(400, 'limit_must_be_1_to_100_before_must_be_positive_integer')
            return self.reply(200, self.server.queue.list_messages(limit, before))
        if self.command == 'POST' and path == '/messages':
            self.auth('producer')
            data = self.read_json()
            data.setdefault('id', 'msg-' + uuid.uuid4().hex)
            if not isinstance(data['id'], str) or not ID.fullmatch(data['id']) or 'payload' not in data:
                raise BadRequest(400, 'id_and_payload_required_id_must_be_1_to_128_url_safe_characters')
            created = self.server.queue.put(data['id'], data['payload'])
            return self.reply(201 if created else 200, dict(id=data['id'], created=created))
        if self.command == 'POST' and path == '/claim':
            self.auth('consumer')
            self.read_json()
            return self.reply(200, dict(message=self.server.queue.claim()))
        match = re.fullmatch(r'/messages/([A-Za-z0-9_-]{1,128})/ack', path)
        if match and self.command == 'POST':
            self.auth('consumer')
            token = self.read_json().get('lease_token')
            if not isinstance(token, str):
                raise BadRequest(400, 'lease_token_required')
            self.server.queue.ack(match[1], token)
            return self.reply(200, dict(ok=True))
        match = re.fullmatch(r'/messages/([A-Za-z0-9_-]{1,128})', path)
        if match and self.command == 'GET':
            self.auth('producer')
            result = self.server.queue.status(match[1])
            return self.reply(200 if result else 404, result or dict(error='not_found'))
        raise BadRequest(404, 'not_found')

    def handle_request(self):
        try:
            self.dispatch()
        except (BadRequest, ServiceError) as e:
            self.reply(e.status, dict(error=e.message))
        except Conflict as e:
            self.reply(409, dict(error=str(e)))
        except sqlite3.Error:
            self.reply(503, dict(error='storage_unavailable'))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    do_GET = do_POST = do_HEAD = do_OPTIONS = handle_request


class RelayServer(ThreadingHTTPServer):
    def service_actions(self):
        if time.monotonic() < getattr(self, 'next_maintenance', 0):
            return
        try:
            self.registry.maintenance()
            self.next_maintenance = time.monotonic() + 3600
        except (sqlite3.Error, OSError):
            print('Muse retention cleanup deferred', flush=True)
            self.next_maintenance = time.monotonic() + 60


def make_server(host, port, db_path, producer_token, consumer_token, lease_seconds=120, public_origin=None, public_send=False):
    if not producer_token or not consumer_token or producer_token == consumer_token:
        raise ValueError('Distinct producer and consumer tokens are required')
    queue = Queue(db_path, lease_seconds)
    http = RelayServer((host, port), Handler)
    http.tokens = dict(producer=producer_token, consumer=consumer_token)
    http.queue = queue
    http.registry = Registry(db_path)
    http.public_origin = public_origin
    http.public_send = public_send
    return http


if __name__ == '__main__':
    http = make_server('0.0.0.0', int(os.environ.get('PORT', '8080')),
        os.environ.get('DB_PATH', '/data/queue.db'),
        os.environ['PRODUCER_TOKEN'], os.environ['CONSUMER_TOKEN'],
        public_origin=os.environ.get('PUBLIC_ORIGIN', 'https://vm-https-check-production.up.railway.app'),
        public_send=os.environ.get('PUBLIC_SEND', 'false').lower() in ('true', '1', 'yes'))
    print(f'Listening on 0.0.0.0:{http.server_port}', flush=True)
    http.serve_forever()
