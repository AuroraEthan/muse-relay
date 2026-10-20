import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path

import server


class API(unittest.TestCase):
    def setUp(self):
        # Wall time cannot expire a 150ms test lease on a busy CI runner.
        # Advance this clock explicitly only when testing expiry/retry semantics.
        clock_patch = patch('queue_store.time.time', return_value=time.time())
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'queue.db')
        self.start()

    def start(self):
        self.http = server.make_server('127.0.0.1', 0, self.db, 'producer', 'consumer', lease_seconds=0.15)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, path, data=None, token='producer', method=None):
        req = urllib.request.Request(self.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def put(self, ident='job1', payload=None):
        return self.request('/messages', {'id': ident, 'payload': payload or {'hello': 'world'}})

    def claim(self):
        return self.request('/claim', {}, 'consumer')[1]['message']

    def ack(self, message):
        return self.request('/messages/' + message['id'] + '/ack',
                            {'lease_token': message['lease_token']}, 'consumer')

    def test_health_and_role_separation(self):
        self.assertEqual(self.request('/health', token='')[0], 200)
        self.assertEqual(self.request('/messages', {}, '')[0], 401)
        self.assertEqual(self.request('/messages', {}, 'consumer')[0], 401)
        self.assertEqual(self.request('/claim', {}, 'producer')[0], 401)

    def test_publish_claim_ack_and_idempotent_ack(self):
        self.assertEqual(self.put()[0], 201)
        m = self.claim()
        self.assertEqual(m['payload'], {'hello': 'world'})
        self.assertIsNone(self.claim())
        self.assertEqual(self.ack(m)[0], 200)
        self.assertEqual(self.ack(m)[0], 200)
        self.assertIsNone(self.claim())
        self.assertEqual(self.request('/messages/job1')[1]['status'], 'acked')

    def test_duplicate_id_is_safe_and_conflicting_payload_rejected(self):
        self.put()
        self.assertEqual(self.put()[0], 200)
        self.assertEqual(self.put(payload={'different': True})[0], 409)

    def test_lease_expiry_and_stale_ack(self):
        self.put()
        first = self.claim()
        self.clock.return_value += 0.2
        second = self.claim()
        self.assertNotEqual(first['lease_token'], second['lease_token'])
        self.assertEqual(self.ack(first)[0], 409)
        self.assertEqual(self.ack(second)[0], 200)

    def test_persists_across_server_restart(self):
        self.put()
        self.stop()
        self.start()
        self.assertEqual(self.claim()['id'], 'job1')

    def test_concurrent_claim_returns_message_once(self):
        self.put()
        with ThreadPoolExecutor(max_workers=4) as pool:
            messages = list(pool.map(lambda _: self.claim(), range(4)))
        self.assertEqual(sum(m is not None for m in messages), 1)

    def test_invalid_payload_and_id(self):
        self.assertEqual(self.request('/messages', {'id': '../x', 'payload': {}})[0], 400)
        self.assertEqual(self.request('/messages', {'id': 'valid'})[0], 400)
        self.assertEqual(self.put(payload={'large': 'x' * 300000})[0], 413)

    def test_worker_http_failure_then_retry_and_ack(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from vm_agent import Agent
        received = []
        fail = [True]
        class Local(BaseHTTPRequestHandler):
            def do_POST(local):
                body = json.loads(local.rfile.read(int(local.headers['Content-Length'])))
                received.append((local.headers['Idempotency-Key'], body))
                local.send_response(503 if fail[0] else 204)
                local.end_headers()
            def log_message(self, *args):
                pass
        target = ThreadingHTTPServer(('127.0.0.1', 0), Local)
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        try:
            self.put()
            agent = Agent(self.url, 'consumer', f'http://127.0.0.1:{target.server_port}/ingest',
                          str(Path(self.temp.name) / 'agent.db'))
            with self.assertRaises(urllib.error.HTTPError):
                agent.poll_once()
            self.assertNotEqual(self.request('/messages/job1')[1]['status'], 'acked')
            self.clock.return_value += 0.2
            fail[0] = False
            self.assertTrue(agent.poll_once())
            self.assertEqual(received[-1], ('job1', {'hello': 'world'}))
            self.assertEqual(self.request('/messages/job1')[1]['status'], 'acked')
        finally:
            target.shutdown(); target.server_close(); thread.join()

    def test_worker_delivered_ledger_survives_restart_and_ack_loss(self):
        from vm_agent import Agent
        self.put()
        ledger = str(Path(self.temp.name) / 'agent.db')
        agent = Agent(self.url, 'consumer', 'http://127.0.0.1:1', ledger)
        m = self.claim()
        agent.remember(m['id'])  # Simulate success persisted before lost server ack.
        self.clock.return_value += 0.2
        restarted = Agent(self.url, 'consumer', 'http://127.0.0.1:1', ledger)
        self.assertTrue(restarted.poll_once())  # Port 1 is never contacted.
        self.assertEqual(self.request('/messages/job1')[1]['status'], 'acked')

    def test_worker_tcp_requires_matching_application_ack(self):
        import socketserver
        from vm_agent import Agent
        received = []
        class Local(socketserver.StreamRequestHandler):
            def handle(local):
                message = json.loads(local.rfile.readline())
                received.append(message)
                local.wfile.write(json.dumps({'id': message['id'], 'ok': True}).encode() + b'\n')
        target = socketserver.TCPServer(('127.0.0.1', 0), Local)
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        try:
            self.put()
            agent = Agent(self.url, 'consumer', f'tcp://127.0.0.1:{target.server_address[1]}',
                          str(Path(self.temp.name) / 'agent.db'))
            self.assertTrue(agent.poll_once())
            self.assertEqual(received, [{'id': 'job1', 'payload': {'hello': 'world'}}])
            self.assertEqual(self.request('/messages/job1')[1]['status'], 'acked')
        finally:
            target.shutdown(); target.server_close(); thread.join()

    def test_worker_rejects_non_loopback_local_target(self):
        from vm_agent import Agent
        with self.assertRaises(ValueError):
            Agent(self.url, 'consumer', 'http://example.com/ingest',
                  str(Path(self.temp.name) / 'agent.db'))

    def test_expired_lease_cannot_ack_without_reclaim(self):
        self.put()
        message = self.claim()
        self.clock.return_value += 0.2
        self.assertEqual(self.ack(message)[0], 409)

    def test_worker_tcp_wrong_ack_is_not_marked_delivered(self):
        import socketserver
        from vm_agent import Agent
        class Local(socketserver.StreamRequestHandler):
            def handle(local):
                local.rfile.readline()
                local.wfile.write(b'{"id":"wrong","ok":true}\n')
        target = socketserver.TCPServer(('127.0.0.1', 0), Local)
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        try:
            self.put()
            agent = Agent(self.url, 'consumer', f'tcp://127.0.0.1:{target.server_address[1]}',
                          str(Path(self.temp.name) / 'agent.db'))
            with self.assertRaises(ValueError):
                agent.poll_once()
            self.assertFalse(agent.known('job1'))
            self.assertNotEqual(self.request('/messages/job1')[1]['status'], 'acked')
        finally:
            target.shutdown(); target.server_close(); thread.join()

    def test_web_root_and_static_assets_have_no_credentials(self):
        for path, expected in [('/', 'text/html'), ('/app.js', 'javascript'),
                               ('/app.css', 'text/css'), ('/api-docs', 'text/html')]:
            with urllib.request.urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected, response.headers['Content-Type'])
                self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
                self.assertNotIn(b'Bearer producer', response.read())
        self.assertEqual(self.request('/producer.env')[0], 404)

    def test_history_requires_producer_and_paginates(self):
        self.assertEqual(self.request('/messages', token='')[0], 401)
        self.assertEqual(self.request('/messages', token='consumer')[0], 401)
        for n in range(3):
            self.put('job' + str(n))
        code, first = self.request('/messages?limit=2')
        self.assertEqual(code, 200)
        self.assertEqual([x['id'] for x in first['messages']], ['job2', 'job1'])
        self.assertEqual(first['stats']['pending'], 3)
        self.assertNotIn('lease_token', first['messages'][0])
        _, second = self.request('/messages?limit=2&before=' + str(first['next_cursor']))
        self.assertEqual([x['id'] for x in second['messages']], ['job0'])
        self.assertIsNone(second['next_cursor'])
        self.assertEqual(self.request('/messages?limit=garbage')[0], 400)

    def test_history_counts_and_detail_payload(self):
        self.put('one')
        self.put('two')
        message = self.claim()
        _, listing = self.request('/messages')
        self.assertEqual(listing['stats'], dict(total=2, pending=1, leased=1, acked=0))
        self.ack(message)
        _, listing = self.request('/messages')
        self.assertEqual(listing['stats']['acked'], 1)
        self.assertEqual(self.request('/messages/one')[1]['payload'], {'hello': 'world'})

    def test_openapi_describes_existing_and_history_endpoints(self):
        code, spec = self.request('/openapi.json', token='')
        self.assertEqual(code, 200)
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertIn('get', spec['paths']['/messages'])
        self.assertIn('post', spec['paths']['/messages'])
        self.assertIn('post', spec['paths']['/claim'])
        self.assertIn('producerAuth', spec['components']['securitySchemes'])

    def test_history_rejects_out_of_range_cursor(self):
        self.assertEqual(self.request('/messages?before=999999999999999999999999')[0], 400)

    def send_text(self, text, key=None, token='producer'):
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'text/plain; charset=utf-8'}
        if key is not None:
            headers['Idempotency-Key'] = key
        req = urllib.request.Request(self.url + '/send', data=text.encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_plain_text_server_assigns_id_and_json_payload(self):
        text = '내일 오전 10시에 결과를 정리해줘.\n한글과 "따옴표" 그대로'
        code, receipt = self.send_text(text)
        self.assertEqual(code, 201)
        self.assertTrue(receipt['id'].startswith('msg-'))
        self.assertEqual(self.request('/messages/' + receipt['id'])[1]['payload'], {'message': text})
        self.assertEqual(self.claim()['payload'], {'message': text})

    def test_plain_text_requires_producer_and_nonempty_text(self):
        self.assertEqual(self.send_text('hello', token='consumer')[0], 401)
        self.assertEqual(self.send_text('  \n ')[0], 400)
        self.assertEqual(self.send_text('x' * 300000)[0], 413)

    def test_plain_text_retry_key_is_transactional(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.send_text('same message', 'retry-key-1'), range(4)))
        self.assertEqual(sum(code == 201 for code, _ in receipts), 1)
        self.assertEqual(len({r['id'] for _, r in receipts}), 1)
        self.assertEqual(self.send_text('different message', 'retry-key-1')[0], 409)
        self.stop(); self.start()
        self.assertEqual(self.send_text('same message', 'retry-key-1')[1]['id'], receipts[0][1]['id'])

    def test_same_text_without_retry_key_is_two_intentional_messages(self):
        first = self.send_text('same text')[1]
        second = self.send_text('same text')[1]
        self.assertNotEqual(first['id'], second['id'])

    def test_json_api_can_omit_id(self):
        code, receipt = self.request('/messages', {'payload': {'message': 'automatic id'}})
        self.assertEqual(code, 201)
        self.assertTrue(receipt['id'].startswith('msg-'))

    def test_plain_sender_helper_needs_only_a_sentence(self):
        from send_text import send_plain
        receipt = send_plain(self.url, 'producer', 'Codex에서 문장만 보냅니다.')
        self.assertEqual(self.request('/messages/' + receipt['id'])[1]['payload'],
                         {'message': 'Codex에서 문장만 보냅니다.'})

    def test_plain_sender_helper_reuses_automatic_retry_key(self):
        from send_text import send_plain
        first = send_plain(self.url, 'producer', 'retry test', request_key='helper-retry')
        second = send_plain(self.url, 'producer', 'retry test', request_key='helper-retry')
        self.assertEqual(first['id'], second['id'])

    def test_sender_cli_keeps_uncertain_send_and_retries_without_duplicate(self):
        import subprocess
        import sys
        failures = [3]
        class LostReply(server.Handler):
            def reply(local, code, value):
                if local.path == '/send' and code in (200, 201) and failures[0]:
                    failures[0] -= 1
                    return super().reply(503, {'error': 'simulated_lost_receipt'})
                return super().reply(code, value)
        self.http.RequestHandlerClass = LostReply
        config = Path(self.temp.name) / 'producer.env'
        config.write_text('SERVER_URL=' + self.url + '\nPRODUCER_TOKEN=producer\n')
        state = Path(self.temp.name) / 'state'
        command = [sys.executable, str(Path(server.__file__).parent / 'send_text.py')]
        failed = subprocess.run(command + ['send', '--env', str(config), '--state', str(state),
            '--text', 'plain CLI sentence'], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertTrue((state / 'pending.json').exists())
        self.assertEqual(self.request('/messages')[1]['stats']['total'], 1)

        retried = subprocess.run(command + ['retry', '--env', str(config), '--state', str(state)],
                                 capture_output=True, text=True)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertFalse(json.loads(retried.stdout)['created'])
        self.assertFalse((state / 'pending.json').exists())
        self.assertEqual(self.request('/messages')[1]['stats']['total'], 1)

    def test_sender_cli_oversize_input_does_not_create_uncertain_send(self):
        import subprocess
        import sys
        config = Path(self.temp.name) / 'producer.env'
        config.write_text('SERVER_URL=' + self.url + '\nPRODUCER_TOKEN=producer\n')
        text_file = Path(self.temp.name) / 'large.txt'
        text_file.write_text('x' * 300000)
        state = Path(self.temp.name) / 'state'
        result = subprocess.run([sys.executable, str(Path(server.__file__).parent / 'send_text.py'),
            'send', '--env', str(config), '--state', str(state), '--file', str(text_file)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse((state / 'pending.json').exists())

    def browser_request(self, path, cookie='', origin=None, token=None, text=None):
        headers = {'Content-Type': 'text/plain; charset=utf-8'}
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(self.url + path, headers=headers,
            data=text.encode() if text is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, error.headers, json.load(error)

    def new_browser_cookie(self):
        code, headers, _ = self.browser_request('/session', token='producer', text='')
        self.assertEqual(code, 200)
        return headers['Set-Cookie'].split(';')[0]

    def test_browser_session_removes_need_for_key_on_following_requests(self):
        cookie = self.new_browser_cookie()
        self.assertEqual(self.browser_request('/session', cookie=cookie)[2]['authenticated'], True)
        code, _, receipt = self.browser_request('/send', cookie=cookie, origin=self.url, text='cookie send')
        self.assertEqual(code, 201)
        self.assertEqual(self.request('/messages/' + receipt['id'])[1]['payload'], {'message': 'cookie send'})
        self.assertEqual(self.browser_request('/messages', cookie=cookie)[0], 200)
        self.assertEqual(self.browser_request('/claim', cookie=cookie, origin=self.url, text='{}')[0], 401)

    def test_browser_session_is_persistent_and_logout_revokes_it(self):
        cookie = self.new_browser_cookie()
        self.stop(); self.start()
        self.assertEqual(self.browser_request('/messages', cookie=cookie)[0], 200)
        self.assertEqual(self.browser_request('/logout', cookie=cookie, origin=self.url, text='')[0], 200)
        self.assertEqual(self.browser_request('/messages', cookie=cookie)[0], 401)

    def test_browser_cookie_writes_require_same_origin(self):
        cookie = self.new_browser_cookie()
        self.assertEqual(self.browser_request('/send', cookie=cookie, origin='https://evil.example', text='no')[0], 403)
        self.assertEqual(self.browser_request('/send', cookie=cookie, text='no origin')[0], 403)
        self.assertEqual(self.request('/messages')[1]['stats']['total'], 0)

    def test_browser_session_cookie_flags_and_key_rotation(self):
        self.http.public_origin = 'https://relay.example'
        code, headers, _ = self.browser_request('/session', token='producer', text='')
        self.assertEqual(code, 200)
        cookie_header = headers['Set-Cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Max-Age=2592000', 'Path=/'):
            self.assertIn(flag, cookie_header)
        cookie = cookie_header.split(';')[0]
        self.http.tokens['producer'] = 'rotated-producer'
        self.assertEqual(self.browser_request('/messages', cookie=cookie)[0], 401)

    def test_expired_browser_session_is_rejected(self):
        token = self.http.queue.issue_session('producer', ttl=-1)
        self.assertEqual(self.browser_request('/session', cookie='relay_session=' + token)[0], 401)

    def test_legacy_public_flag_never_enables_anonymous_send(self):
        self.http.public_send = True
        self.assertFalse(self.browser_request('/config')[2]['public_send'])
        self.assertEqual(self.browser_request('/send', text='anonymous')[0],401)
        self.assertEqual(self.browser_request('/send', origin='https://external.example', text='cross origin')[0],401)
        self.assertEqual(self.browser_request('/messages')[0],401)

    def test_plain_helper_requires_producer_key_even_with_stale_public_flag(self):
        from send_text import send_plain
        self.http.public_send = True
        with self.assertRaises(Exception): send_plain(self.url, '', 'anonymous helper')
        self.assertTrue(send_plain(self.url, 'producer', 'authenticated helper')['created'])



if __name__ == '__main__':
    unittest.main()
