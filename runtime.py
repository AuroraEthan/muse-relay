"""Small shared helpers; Python standard library only."""
import json
import os
import re
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env(path):
    if path is None:
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().isidentifier():
            raise ValueError('Invalid env file line')
        os.environ.setdefault(key.strip(), value.strip())


def check_server_url(url):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('SERVER_URL must not include credentials, query or fragment')
    if parsed.scheme != 'https' and not (
        parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('SERVER_URL must use HTTPS (HTTP allowed only for loopback tests)')
    if not parsed.hostname or not (parsed.path in ('', '/') or re.fullmatch(r'/api/muses/m_[a-f0-9]{32}', parsed.path)):
        raise ValueError('SERVER_URL must be an origin or an exact Muse API prefix')
    return url.rstrip('/')


def json_request(url, data, token, timeout=15):
    request = urllib.request.Request(url,
        data=json.dumps(data, ensure_ascii=False, allow_nan=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    # Do not forward credentials through redirects.
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        return json.loads(response.read(524288))
