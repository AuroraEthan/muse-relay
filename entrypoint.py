"""Make the mounted data directory writable, then run as an unprivileged user."""
import os
from pathlib import Path
import runpy

data = Path(os.environ.get('DB_PATH', '/data/queue.db')).parent
data.mkdir(parents=True, exist_ok=True)
if os.geteuid() == 0:
    os.chown(data, 10001, 10001)
    # Existing SQLite WAL files also need to be writable after a restart.
    for name in ('queue.db', 'queue.db-wal', 'queue.db-shm'):
        path = data / name
        if path.exists():
            os.chown(path, 10001, 10001)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
runpy.run_path('/app/server.py', run_name='__main__')
