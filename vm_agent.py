"""Poll the queue and deliver to a configured loopback HTTP/TCP receiver."""
import argparse
import json
import logging
import os
from pathlib import Path
import socket
import sqlite3
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from runtime import NoRedirect, check_server_url, json_request, load_env


class Agent:
    def __init__(self, server_url, token, target, state_path, timeout=15,
                 tcp_ack=True, local_token=''):
        self.server_url = check_server_url(server_url)
        self.token, self.target = token, urlsplit(target)
        if not token:
            raise ValueError('CONSUMER_TOKEN is required')
        if self.target.scheme not in ('http', 'https', 'tcp') or self.target.hostname not in (
                '127.0.0.1', 'localhost', '::1'):
            raise ValueError('LOCAL_URL must use http/https/tcp and a loopback host')
        if self.target.username or self.target.password or self.target.fragment:
            raise ValueError('LOCAL_URL must not include credentials or fragment')
        if self.target.scheme == 'tcp' and (not self.target.port or self.target.path or self.target.query):
            raise ValueError('TCP target format: tcp://127.0.0.1:PORT')
        if not 0 < timeout <= 30:
            raise ValueError('LOCAL_TIMEOUT must be 0..30 seconds (server lease: 120 seconds)')
        self.timeout, self.tcp_ack, self.local_token = timeout, tcp_ack, local_token

        self.state_path = state_path
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(state_path)
        try:
            with db:
                db.execute('''CREATE TABLE IF NOT EXISTS delivered (
                    source TEXT NOT NULL, id TEXT NOT NULL, PRIMARY KEY(source,id))''')
        finally:
            db.close()

    def known(self, ident):
        db = sqlite3.connect(self.state_path)
        try:
            return db.execute('SELECT 1 FROM delivered WHERE source=? AND id=?',
                              (self.server_url, ident)).fetchone() is not None
        finally:
            db.close()

    def remember(self, ident):
        db = sqlite3.connect(self.state_path)
        try:
            with db:
                db.execute('INSERT OR IGNORE INTO delivered(source,id) VALUES (?,?)',
                           (self.server_url, ident))
        finally:
            db.close()

    def deliver(self, message):
        if self.target.scheme == 'tcp':
            body = json.dumps({'id': message['id'], 'payload': message['payload']},
                              ensure_ascii=False, allow_nan=False).encode() + b'\n'
            with socket.create_connection((self.target.hostname, self.target.port), self.timeout) as conn:
                conn.settimeout(self.timeout)
                conn.sendall(body)
                if self.tcp_ack:
                    with conn.makefile('rb') as stream:
                        line = stream.readline(4097)
                    if len(line) > 4096 or not line.endswith(b'\n'):
                        raise ValueError('TCP receiver must reply with one JSON acknowledgement line')
                    ack = json.loads(line)
                    if not isinstance(ack, dict) or ack.get('id') != message['id'] or ack.get('ok') is not True:
                        raise ValueError('TCP acknowledgement must have matching id and ok=true')
        else:
            body = json.dumps(message['payload'], ensure_ascii=False, allow_nan=False).encode()
            headers = {'Content-Type': 'application/json', 'Idempotency-Key': message['id'],
                       'X-Message-ID': message['id']}
            if self.local_token:
                headers['Authorization'] = 'Bearer ' + self.local_token
            request = urllib.request.Request(self.target.geturl(), data=body, headers=headers)
            # Local calls bypass environment HTTP proxies and never follow redirects.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise ValueError('Local HTTP receiver did not return 2xx')

    def poll_once(self):
        message = json_request(self.server_url + '/claim', {}, self.token)['message']
        if message is None:
            return False
        if not self.known(message['id']):
            self.deliver(message)
            self.remember(message['id'])
        json_request(self.server_url + '/messages/' + message['id'] + '/ack',
                     {'lease_token': message['lease_token']}, self.token)
        logging.info('Acknowledged message %s', message['id'])
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', help='KEY=VALUE config file; existing environment takes precedence')
    parser.add_argument('--once', action='store_true', help='Poll once and exit; useful for diagnostics')
    args = parser.parse_args()
    load_env(args.env)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    agent = Agent(os.environ['SERVER_URL'], os.environ['CONSUMER_TOKEN'], os.environ['LOCAL_URL'],
                  os.environ.get('STATE_PATH', './vm-state/delivered.db'),
                  float(os.environ.get('LOCAL_TIMEOUT', '15')),
                  os.environ.get('TCP_ACK', 'required') != 'none',
                  os.environ.get('LOCAL_HTTP_TOKEN', ''))
    interval = float(os.environ.get('POLL_INTERVAL', '5'))
    if interval < 1:
        raise ValueError('POLL_INTERVAL must be at least 1 second')
    logging.info('Worker started; poll interval %ss', interval)
    while True:
        try:
            agent.poll_once()
        except (OSError, ValueError, sqlite3.Error, urllib.error.URLError) as error:
            if isinstance(error, urllib.error.HTTPError):
                logging.error('HTTP %s; not acknowledged, will retry', error.code)
            else:
                logging.error('%s; not acknowledged, will retry', type(error).__name__)
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        time.sleep(interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
