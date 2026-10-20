"""Accounts, ownership and device pairing; each Muse has its own durable queue."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from queue_store import Queue, Conflict

SESSION_TTL = 30 * 86400
MUSE_ID = r'm_[a-f0-9]{32}'


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class MuseQueue(Queue):
    pending_limit = 1000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prune()

    def prune(self):
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                cutoff = time.time() - 30 * 86400
                db.execute('DELETE FROM send_requests WHERE message_id IN (SELECT id FROM messages WHERE acked < ?)', (cutoff,))
                db.execute('DELETE FROM messages WHERE acked < ?', (cutoff,))
        finally:
            db.close()

    def put_text(self, text, request_key=None):
        encoded = json.dumps({'message': text}, sort_keys=True, ensure_ascii=False, allow_nan=False)
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                # Retain delivered messages and their retry keys for thirty days.
                cutoff = time.time() - 30 * 86400
                db.execute('DELETE FROM send_requests WHERE message_id IN (SELECT id FROM messages WHERE acked < ?)', (cutoff,))
                db.execute('DELETE FROM messages WHERE acked < ?', (cutoff,))
                if request_key:
                    row = db.execute('SELECT m.id,m.payload FROM send_requests r JOIN messages m ON m.id=r.message_id WHERE r.request_key=?', (request_key,)).fetchone()
                    if row:
                        if row['payload'] != encoded:
                            raise Conflict('retry_key_already_used_with_different_text')
                        return row['id'], False
                count = db.execute('SELECT count(*) FROM messages WHERE acked IS NULL').fetchone()[0]
                if count >= self.pending_limit:
                    raise ServiceError(429, 'muse_pending_limit_1000')
                ident = 'msg-' + uuid.uuid4().hex
                db.execute('INSERT INTO messages(id,payload,created) VALUES(?,?,?)', (ident, encoded, time.time()))
                if request_key:
                    db.execute('INSERT INTO send_requests(request_key,message_id) VALUES(?,?)', (request_key, ident))
                return ident, True
        finally:
            db.close()


class Registry:
    def __init__(self, path):
        self.path = str(path)
        self.queue_dir = Path(path).parent / (Path(path).stem + '-muses')
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS muse_users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS muse_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS muse_session_expiry ON muse_sessions(expires);
                CREATE TABLE IF NOT EXISTS muses (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                    public_send INTEGER NOT NULL, created REAL NOT NULL,
                    pair_hash TEXT UNIQUE, pair_expires REAL,
                    device_hash TEXT, connected_at REAL, last_seen REAL);
                CREATE INDEX IF NOT EXISTS muse_owner ON muses(owner);
                CREATE TABLE IF NOT EXISTS muse_rates (
                    key TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(key, window));
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rate(self, key, limit, period=60):
        now = int(time.time()); window = now // period
        key = digest(key) + ':' + str(period)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM muse_rates WHERE window < ? AND key LIKE ?', (window - 2, '%:' + str(period)))
            count = db.execute('SELECT count FROM muse_rates WHERE key=? AND window=?', (key, window)).fetchone()
            if count and count[0] >= limit:
                raise ServiceError(429, 'rate_limit_try_again_later')
            db.execute('INSERT INTO muse_rates(key,window,count) VALUES(?,?,1) ON CONFLICT(key,window) DO UPDATE SET count=count+1', (key, window))

    @staticmethod
    def credentials(username, password):
        if not isinstance(username, str) or not re.fullmatch(r'[a-z0-9_]{3,32}', username):
            raise ServiceError(400, 'username_lowercase_letters_digits_underscore_3_to_32')
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ServiceError(400, 'password_12_to_128_characters')

    @staticmethod
    def password_hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64*1024*1024).hex()

    def signup(self, username, password):
        self.credentials(username, password)
        salt = secrets.token_hex(16); hashed = self.password_hash(password, salt)
        user = dict(id='u_' + uuid.uuid4().hex, username=username)
        try:
            with self.connection() as db:
                db.execute('INSERT INTO muse_users VALUES(?,?,?,?,?)', (user['id'], username, salt, hashed, time.time()))
        except sqlite3.IntegrityError:
            raise ServiceError(409, 'username_unavailable')
        return user

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 32 or len(password) > 128:
            raise ServiceError(401, 'invalid_credentials')
        with self.connection() as db:
            row = db.execute('SELECT * FROM muse_users WHERE username=?', (username,)).fetchone()
        # Always do the password derivation to avoid a fast unknown-user branch.
        salt = row['salt'] if row else '00' * 16
        hashed = self.password_hash(password, salt)
        if not row or not hmac.compare_digest(hashed, row['password_hash']):
            raise ServiceError(401, 'invalid_credentials')
        return dict(id=row['id'], username=row['username'])

    def issue_session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('DELETE FROM muse_sessions WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO muse_sessions VALUES(?,?,?)', (digest(token), user_id, time.time()+SESSION_TTL))
        return token

    def user(self, token):
        if not token or len(token) > 100:
            return None
        with self.connection() as db:
            row = db.execute('SELECT u.id,u.username FROM muse_sessions s JOIN muse_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?', (digest(token),time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connection() as db:
            db.execute('DELETE FROM muse_sessions WHERE token_hash=?', (digest(token),))

    def create(self, owner, name, public_send):
        self.validate_settings(name, public_send)
        mid = 'm_' + uuid.uuid4().hex
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM muses WHERE owner=?', (owner,)).fetchone()[0] >= 3:
                raise ServiceError(429, 'maximum_3_muses_per_account')
            db.execute('INSERT INTO muses(id,owner,name,public_send,created) VALUES(?,?,?,?,?)', (mid,owner,name.strip(),int(public_send),time.time()))
        return self.owned(mid, owner)

    @staticmethod
    def validate_settings(name, public_send):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c)<32 for c in name):
            raise ServiceError(400, 'muse_name_1_to_60_characters')
        if not isinstance(public_send, bool):
            raise ServiceError(400, 'public_send_must_be_boolean')

    @staticmethod
    def view(row, owner=False):
        if not row: return None
        result = dict(id=row['id'], name=row['name'], public_send=bool(row['public_send']))
        if owner:
            result.update(created=row['created'], device_connected=bool(row['device_hash']),
                          connected_at=row['connected_at'], last_seen=row['last_seen'])
        return result

    def info(self, mid):
        with self.connection() as db:
            row = db.execute('SELECT * FROM muses WHERE id=?', (mid,)).fetchone()
        return self.view(row)

    def owned(self, mid, owner):
        with self.connection() as db:
            row = db.execute('SELECT * FROM muses WHERE id=? AND owner=?', (mid, owner)).fetchone()
        if not row: raise ServiceError(404, 'muse_not_found')
        return self.view(row, True)

    def list(self, owner):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM muses WHERE owner=? ORDER BY created', (owner,)).fetchall()
        return [self.view(row, True) for row in rows]

    def settings(self, mid, owner, name, public_send):
        self.validate_settings(name, public_send)
        with self.connection() as db:
            changed = db.execute('UPDATE muses SET name=?,public_send=? WHERE id=? AND owner=?', (name.strip(),int(public_send),mid,owner)).rowcount
            if not changed: raise ServiceError(404, 'muse_not_found')
        return self.owned(mid, owner)

    def pairing(self, mid, owner):
        code = secrets.token_hex(8).upper()
        with self.connection() as db:
            changed = db.execute('UPDATE muses SET pair_hash=?,pair_expires=? WHERE id=? AND owner=?', (digest(code),time.time()+600,mid,owner)).rowcount
            if not changed: raise ServiceError(404, 'muse_not_found')
        return dict(code=code, expires_in=600)

    def pair(self, code):
        if not isinstance(code, str) or not re.fullmatch(r'[A-Fa-f0-9]{16}', code.strip()):
            raise ServiceError(401, 'invalid_or_expired_pairing_code')
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id FROM muses WHERE pair_hash=? AND pair_expires>?', (digest(code.strip().upper()),time.time())).fetchone()
            if not row: raise ServiceError(401, 'invalid_or_expired_pairing_code')
            db.execute('UPDATE muses SET pair_hash=NULL,pair_expires=NULL,device_hash=?,connected_at=?,last_seen=NULL WHERE id=?', (digest(token),time.time(),row['id']))
        return dict(muse_id=row['id'], device_token=token)

    def device(self, mid, token):
        if not token or len(token) > 100: return False
        with self.connection() as db:
            row = db.execute('SELECT device_hash FROM muses WHERE id=?', (mid,)).fetchone()
        return bool(row and row['device_hash'] and hmac.compare_digest(row['device_hash'],digest(token)))

    def seen(self, mid):
        with self.connection() as db:
            db.execute('UPDATE muses SET last_seen=? WHERE id=?', (time.time(),mid))

    def revoke(self, mid, owner):
        with self.connection() as db:
            changed=db.execute('UPDATE muses SET device_hash=NULL,pair_hash=NULL,pair_expires=NULL,last_seen=NULL WHERE id=? AND owner=?', (mid,owner)).rowcount
            if not changed: raise ServiceError(404, 'muse_not_found')

    def maintenance(self):
        # Queue access also prunes immediately; hourly sweeping covers idle Muses.
        for path in self.queue_dir.glob('m_*.db'):
            if re.fullmatch(MUSE_ID, path.stem):
                MuseQueue(path).prune()
        with self.connection() as db:
            db.execute('DELETE FROM muse_sessions WHERE expires<=?', (time.time(),))

    def queue(self, mid):
        if not re.fullmatch(MUSE_ID, mid) or not self.info(mid):
            raise ServiceError(404, 'muse_not_found')
        return MuseQueue(self.queue_dir / (mid + '.db'))
