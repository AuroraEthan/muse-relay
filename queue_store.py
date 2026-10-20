"""Durable queue with transactional leases."""
import json
import hashlib
import secrets
import sqlite3
import time
import uuid
from pathlib import Path


class Conflict(Exception):
    pass


class Queue:
    def __init__(self, path, lease_seconds=120):
        self.path, self.lease_seconds = path, lease_seconds
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = self.connect()
        try:
            with db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL,
                    acked REAL, lease_token TEXT, lease_until REAL NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0)''')
                db.execute('CREATE INDEX IF NOT EXISTS pending ON messages(acked, created)')
                db.execute('''CREATE TABLE IF NOT EXISTS send_requests (
                    request_key TEXT PRIMARY KEY, message_id TEXT NOT NULL UNIQUE)''')
                db.execute('''CREATE TABLE IF NOT EXISTS browser_sessions (
                    token_hash TEXT PRIMARY KEY, issuer_hash TEXT NOT NULL, expires REAL NOT NULL)''')
        finally:
            db.close()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def issue_session(self, issuer, ttl=2592000):
        token = secrets.token_urlsafe(32)
        db = self.connect()
        try:
            with db:
                db.execute('DELETE FROM browser_sessions WHERE expires <= ?', (time.time(),))
                db.execute('INSERT INTO browser_sessions(token_hash,issuer_hash,expires) VALUES(?,?,?)',
                    (hashlib.sha256(token.encode()).hexdigest(), hashlib.sha256(issuer.encode()).hexdigest(), time.time() + ttl))
        finally:
            db.close()
        return token

    def valid_session(self, token, issuer):
        if not token:
            return False
        db = self.connect()
        try:
            return db.execute('''SELECT 1 FROM browser_sessions
                WHERE token_hash=? AND issuer_hash=? AND expires>?''',
                (hashlib.sha256(token.encode()).hexdigest(), hashlib.sha256(issuer.encode()).hexdigest(), time.time())).fetchone() is not None
        finally:
            db.close()

    def revoke_session(self, token):
        db = self.connect()
        try:
            with db:
                db.execute('DELETE FROM browser_sessions WHERE token_hash=?',
                           (hashlib.sha256(token.encode()).hexdigest(),))
        finally:
            db.close()

    def put(self, ident, payload):
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT payload FROM messages WHERE id=?', (ident,)).fetchone()
                if row:
                    if row['payload'] != encoded:
                        raise Conflict('id_already_used_with_different_payload')
                    return False
                db.execute('INSERT INTO messages(id,payload,created) VALUES (?,?,?)',
                           (ident, encoded, time.time()))
                return True
        finally:
            db.close()

    def claim(self):
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                now = time.time()
                row = db.execute('''SELECT * FROM messages WHERE acked IS NULL
                    AND lease_until <= ? ORDER BY created, rowid LIMIT 1''', (now,)).fetchone()
                if not row:
                    return None
                token = secrets.token_urlsafe(32)
                until = now + self.lease_seconds
                db.execute('''UPDATE messages SET lease_token=?, lease_until=?,
                    attempts=attempts+1 WHERE id=?''', (token, until, row['id']))
                return dict(id=row['id'], payload=json.loads(row['payload']),
                            lease_token=token, lease_until=until, attempts=row['attempts'] + 1)
        finally:
            db.close()

    def put_text(self, text, request_key=None):
        encoded = json.dumps({'message': text}, sort_keys=True, ensure_ascii=False, allow_nan=False)
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                if request_key:
                    existing = db.execute('''SELECT m.id,m.payload FROM send_requests r
                        JOIN messages m ON m.id=r.message_id WHERE r.request_key=?''', (request_key,)).fetchone()
                    if existing:
                        if existing['payload'] != encoded:
                            raise Conflict('retry_key_already_used_with_different_text')
                        return existing['id'], False
                ident = 'msg-' + uuid.uuid4().hex
                db.execute('INSERT INTO messages(id,payload,created) VALUES(?,?,?)',
                           (ident, encoded, time.time()))
                if request_key:
                    db.execute('INSERT INTO send_requests(request_key,message_id) VALUES(?,?)',
                               (request_key, ident))
                return ident, True
        finally:
            db.close()

    def ack(self, ident, token):
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT * FROM messages WHERE id=?', (ident,)).fetchone()
                if not row or not token or row['lease_token'] != token:
                    raise Conflict('invalid_or_stale_lease')
                if row['acked'] is not None:
                    return
                if row['lease_until'] <= time.time():
                    raise Conflict('lease_expired')
                db.execute('UPDATE messages SET acked=? WHERE id=?', (time.time(), ident))
        finally:
            db.close()

    def status(self, ident):
        db = self.connect()
        try:
            row = db.execute('SELECT * FROM messages WHERE id=?', (ident,)).fetchone()
            if row is None:
                return None
            state = 'acked' if row['acked'] is not None else (
                'leased' if row['lease_until'] > time.time() else 'pending')
            return dict(id=ident, status=state, attempts=row['attempts'], created=row['created'],
                        acked_at=row['acked'], payload=json.loads(row['payload']))
        finally:
            db.close()

    def list_messages(self, limit=25, before=None):
        db = self.connect()
        try:
            now = time.time()
            counts = db.execute('''SELECT count(*) AS total,
                coalesce(sum(acked IS NOT NULL),0) AS acked,
                coalesce(sum(acked IS NULL AND lease_until > ?),0) AS leased,
                coalesce(sum(acked IS NULL AND lease_until <= ?),0) AS pending
                FROM messages''', (now, now)).fetchone()
            where = 'WHERE rowid < ?' if before is not None else ''
            params = (before, limit + 1) if before is not None else (limit + 1,)
            rows = db.execute(f'SELECT rowid AS cursor, * FROM messages {where} ORDER BY rowid DESC LIMIT ?',
                              params).fetchall()
            items = []
            for row in rows[:limit]:
                payload = json.loads(row['payload'])
                preview = payload.get('message', payload.get('text', payload)) if isinstance(payload, dict) else payload
                if not isinstance(preview, str):
                    preview = json.dumps(preview, ensure_ascii=False)
                state = 'acked' if row['acked'] is not None else ('leased' if row['lease_until'] > now else 'pending')
                items.append(dict(id=row['id'], status=state, attempts=row['attempts'],
                                  created=row['created'], acked_at=row['acked'], preview=preview[:180]))
            return dict(messages=items, stats=dict(counts),
                        next_cursor=rows[limit - 1]['cursor'] if len(rows) > limit else None)
        finally:
            db.close()
