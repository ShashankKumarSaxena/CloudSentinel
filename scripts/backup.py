"""Private local backup and offline restore for the database and model artifacts."""
import argparse
from datetime import datetime, timezone
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def backup(database: Path, destination: Path):
    if not database.is_file():
        raise ValueError('Database not found; nothing was backed up.')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory() as workspace:
        staging = Path(workspace)
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(staging / 'cloudsentinel.db')) as target:
            source.backup(target)
            with target:
                tables = {r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'sessions' in tables:
                    target.execute('DELETE FROM sessions')
            # Consolidate a copied WAL database before archiving its main file.
            target.execute('PRAGMA journal_mode=DELETE')
        model_dir = database.parent / 'models'
        if model_dir.exists():
            copied = staging / 'models'
            copied.mkdir()
            pointer = model_dir / 'active.json'
            if pointer.exists():
                shutil.copy2(pointer, copied / 'active.json')
            for artifact in model_dir.glob('*.joblib'):
                shutil.copy2(artifact, copied / artifact.name)
        files = sorted(p for p in staging.rglob('*') if p.is_file())
        manifest = {'format': 'cloudsentinel-backup-v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                    'files': {str(p.relative_to(staging)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                    'sessions_removed': True}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        handle = tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.backup-', delete=False)
        temporary = Path(handle.name)
        try:
            with handle, tarfile.open(fileobj=handle, mode='w:gz') as archive:
                for file in sorted(p for p in staging.rglob('*') if p.is_file()):
                    archive.add(file, arcname=str(file.relative_to(staging)))
            temporary.chmod(0o600)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def restore(archive_path: Path, database: Path):
    if database.exists() or (database.parent / 'models').exists():
        raise ValueError('Restore requires an empty destination. Stop the service and choose a fresh data directory.')
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = database.parent / (database.name + '.monitor.lock')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Stop the server before restoring its data directory.') from None
        with tempfile.TemporaryDirectory(dir=database.parent) as workspace:
            staging = Path(workspace)
            with tarfile.open(archive_path, 'r:gz') as archive:
                members = archive.getmembers()
                total = sum(m.size for m in members)
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Backup exceeds the 1 GB restore limit.')
                names = set()
                for member in members:
                    path = Path(member.name)
                    allowed = member.name in ('manifest.json', 'cloudsentinel.db') or (len(path.parts) == 2 and path.parts[0] == 'models' and (path.name == 'active.json' or path.suffix == '.joblib'))
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or not allowed or member.name in names:
                        raise ValueError('Backup contains an unsupported or unsafe path.')
                    names.add(member.name)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError('Backup contains an unreadable file.')
                    destination = staging / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source, destination.open('wb') as stream:
                        shutil.copyfileobj(source, stream)
                    destination.chmod(0o600)
            if not {'manifest.json', 'cloudsentinel.db'}.issubset(names):
                raise ValueError('Backup must contain a database and manifest.')
            manifest = json.loads((staging / 'manifest.json').read_text())
            if manifest.get('format') != 'cloudsentinel-backup-v1' or set(manifest.get('files', {})) != names - {'manifest.json'}:
                raise ValueError('Backup manifest is invalid.')
            for filename, expected in manifest['files'].items():
                if hashlib.sha256((staging / filename).read_bytes()).hexdigest() != expected:
                    raise ValueError('Backup checksum verification failed.')
            staged_db = staging / 'cloudsentinel.db'
            with closing(sqlite3.connect(staged_db)) as conn:
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup database failed its integrity check.')
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'sessions' in tables:
                    conn.execute('DELETE FROM sessions')
                if 'schedules' in tables:
                    # Restores never resume cloud collection before the owner reviews scope.
                    conn.execute("UPDATE schedules SET enabled=0,lease_until=NULL,last_status='restored'")
                    conn.execute("UPDATE monitor_runs SET status='interrupted',finished_at=? WHERE status='running'", (datetime.now(timezone.utc).isoformat(),))
                if 'alerts' in tables:
                    conn.execute("UPDATE alerts SET delivery='inbox_only',next_delivery=NULL WHERE delivery IN ('pending','sending')")
                conn.commit()
                conn.execute('PRAGMA journal_mode=DELETE')
            models = staging / 'models'
            if models.exists():
                if (database.parent / 'models').exists():
                    raise ValueError('Restore requires an empty model directory.')
                models.rename(database.parent / 'models')
            staged_db.replace(database)
            database.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--database', type=Path, default=Path(os.environ.get('CLOUDSENTINEL_DB', ROOT / '.runtime/cloudsentinel.db')))
    args = parser.parse_args()
    try:
        if args.action == 'backup':
            backup(args.database, args.archive)
            print('Backup created with private file permissions. Sessions were excluded.')
        else:
            restore(args.archive, args.database)
            print('Data restored. Sign in again and review paused schedules before enabling them.')
    except (ValueError, OSError, sqlite3.Error, tarfile.TarError, json.JSONDecodeError):
        raise SystemExit('Backup operation failed. Check the paths, archive integrity, available storage, and whether the destination is empty.') from None


if __name__ == '__main__':
    main()
