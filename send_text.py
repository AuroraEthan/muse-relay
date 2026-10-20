"""Send natural-language text. IDs and the VM JSON envelope are assigned by the server."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid
from runtime import NoRedirect, check_server_url, load_env


def send_plain(server_url, token, text, request_key=None, attempts=3):
    origin = check_server_url(server_url)
    if not text.strip():
        raise ValueError('Message text must not be empty')
    if len(json.dumps({'message': text}, ensure_ascii=False).encode()) > 262144:
        raise ValueError('Message exceeds 256 KiB after encoding')
    key = request_key or uuid.uuid4().hex
    for attempt in range(attempts):
        request = urllib.request.Request(origin + '/send', data=text.encode('utf-8'), headers={
            **({'Authorization': 'Bearer ' + token} if token else {}), 'Content-Type': 'text/plain; charset=utf-8',
            'Idempotency-Key': key})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
                return json.loads(response.read(8192))
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts - 1:
                raise
        time.sleep(0.5 * (2 ** attempt))


def save_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('send', 'retry', 'status'), nargs='?', default='send')
    parser.add_argument('--env', default='producer.env')
    parser.add_argument('--state', help='Private local delivery receipts directory')
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument('--text')
    inputs.add_argument('--file', help='UTF-8 plain text file; otherwise read stdin')
    args = parser.parse_args()
    if Path(args.env).exists():
        load_env(args.env)
    elif args.env != 'producer.env':
        raise SystemExit('The specified configuration file does not exist.')
    origin = check_server_url(os.environ.get('SERVER_URL', 'https://vm-https-check-production.up.railway.app'))
    token = os.environ.get('PRODUCER_TOKEN', '')
    send_token = '' if os.environ.get('PUBLIC_SEND', '').lower() in ('true', '1', 'yes') else token
    state = Path(args.state) if args.state else Path(args.env).resolve().parent / 'relay-state'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending, last = state / 'pending.json', state / 'last.json'
    # Lock only our own directory; do not delete another process's lock.
    lock = state / 'sending.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise SystemExit('Another send is in progress, or a prior process exited unexpectedly. Check it before removing the lock.')
    try:
        if args.action == 'status':
            if not token:
                raise SystemExit('Sending is public; delivery history requires an administrator connection.')
            if not last.exists():
                raise SystemExit('No successful send receipt is recorded yet.')
            receipt = json.loads(last.read_text())
            if receipt['server'] != origin:
                raise SystemExit('Receipt belongs to a different server.')
            req = urllib.request.Request(origin + '/messages/' + receipt['id'],
                    headers={'Authorization': 'Bearer ' + token})
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
                result = json.load(response)
            print(json.dumps({key: result[key] for key in ('id', 'status', 'attempts')}))
            return
        if args.action == 'retry':
            if not pending.exists():
                raise SystemExit('There is no uncertain send to retry.')
            task = json.loads(pending.read_text())
        else:
            text = args.text if args.text is not None else (Path(args.file).read_text(encoding='utf-8') if args.file else sys.stdin.read())
            if not text.strip():
                raise SystemExit('Message text must not be empty.')
            if len(json.dumps({'message': text}, ensure_ascii=False).encode()) > 262144:
                raise SystemExit('Message exceeds 256 KiB after encoding.')
            if pending.exists():
                raise SystemExit('A previous send is uncertain. Use retry before starting another message.')
            task = dict(server=origin, text=text, request_key=uuid.uuid4().hex)
            save_private(pending, task)
        if task['server'] != origin:
            raise SystemExit('Pending send belongs to a different server.')
        try:
            result = send_plain(origin, send_token, task['text'], task['request_key'])
        except (OSError, ValueError) as error:
            code = (' HTTP ' + str(error.code)) if isinstance(error, urllib.error.HTTPError) else ''
            # A definite rejection did not create a message; ambiguous network/server failures retain the same request key.
            if isinstance(error, urllib.error.HTTPError) and error.code in (400, 401, 403, 404, 413, 415):
                pending.unlink()
                raise SystemExit('Send rejected.' + code + ' Check credentials, server version or message size.')
            raise SystemExit('Send not confirmed.' + code + ' Pending text and retry key were kept. Use retry; do not create another send.')
        save_private(last, dict(server=origin, id=result['id']))
        pending.unlink()
        print(json.dumps(result))
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
