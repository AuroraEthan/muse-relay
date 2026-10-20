"""Verify a CI container using temporary data and known test-only keys."""
import io
import json
import time
import urllib.error
import urllib.request
import zipfile

ORIGIN = 'http://127.0.0.1:18080'


def get(path, expected=200):
    try:
        response = urllib.request.urlopen(ORIGIN + path, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    assert response.status == expected, (path, response.status)
    return response.read()


for attempt in range(30):
    try:
        assert json.loads(get('/health'))['ok'] is True
        break
    except (OSError, AssertionError):
        if attempt == 29:
            raise
        time.sleep(0.5)

assert b'Muse Relay' in get('/')
assert b'ConnectionPrompts' in get('/muse-setup.js')
assert b'RelayTest' in get('/muse-test.js')
assert b'VM' in get('/legacy')
assert json.loads(get('/openapi.json'))['info']['version'] == '2.0.0'
get('/api/auth/me', 401)
get('/api/muses', 401)
get('/producer.env', 404)
get('/vm.env', 404)
with zipfile.ZipFile(io.BytesIO(get('/downloads/muse-agent.zip'))) as archive:
    assert {'muse_agent.py', 'vm_agent.py', 'runtime.py', 'START.md'} <= set(archive.namelist())
    assert not any(name.endswith('.env') for name in archive.namelist())
print('Container health, Muse assets, API authentication and secret-file boundaries: PASS')
