"""Back up/restore the production Compose workspace without putting secrets in argv."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.infrastructure.archives import read_archive, write_archive

RESTORE_POLICY = b"""
BEGIN;
DELETE FROM sessions;
DELETE FROM worker_heartbeat;
UPDATE schedules SET enabled=0,lease_until=NULL,last_status='restored';
UPDATE monitor_runs SET status='interrupted',finished_at=:'restored_at' WHERE status='running';
UPDATE collection_jobs SET status='cancelled',finished_at=:'restored_at',error='Paused by offline restore' WHERE status IN ('pending','running');
UPDATE alerts SET delivery='inbox_only',next_delivery=NULL WHERE delivery IN ('pending','sending');
COMMIT;
"""


def compose(project, *arguments, **kwargs):
    command = ["docker", "compose"]
    environment_file = ROOT / "deploy/production/.env"
    if environment_file.exists():
        command += ["--env-file", str(environment_file)]
    command += ["-f", str(ROOT / "deploy/production/compose.yaml")]
    if project:
        command += ["-p", project]
    return subprocess.run([*command, *arguments], check=True, timeout=600, **kwargs)


def backup(archive, project=None):
    if archive.exists():
        raise ValueError("Use a new archive filename.")
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        with (staging / "database.dump").open("wb") as stream:
            compose(
                project,
                "exec",
                "-T",
                "database",
                "pg_dump",
                "--username",
                "cloudsentinel_owner",
                "--dbname",
                "cloudsentinel",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                stdout=stream,
                stderr=subprocess.PIPE,
            )
        compose(
            project,
            "cp",
            "worker:/var/lib/cloudsentinel/models",
            str(staging / "models"),
            capture_output=True,
        )
        write_archive(staging, archive)


def restore(archive, project=None):
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        read_archive(archive, staging)
        running = compose(
            project, "ps", "--status", "running", "--services", capture_output=True, text=True
        ).stdout.split()
        if any(service in running for service in ("api", "worker")):
            raise ValueError("Stop the API and worker before restoring.")
        count = compose(
            project,
            "exec",
            "-T",
            "database",
            "psql",
            "--username",
            "cloudsentinel_owner",
            "--dbname",
            "cloudsentinel",
            "--tuples-only",
            "--no-align",
            "--command",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'",
            capture_output=True,
            text=True,
        ).stdout.strip()
        if count != "0":
            raise ValueError("Restore requires an empty database in a fresh deployment project.")
        with (staging / "database.dump").open("rb") as stream:
            compose(
                project,
                "exec",
                "-T",
                "database",
                "pg_restore",
                "--username",
                "cloudsentinel_owner",
                "--role",
                "cloudsentinel",
                "--dbname",
                "cloudsentinel",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                stdin=stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        compose(
            project,
            "exec",
            "-T",
            "database",
            "psql",
            "--username",
            "cloudsentinel_owner",
            "--dbname",
            "cloudsentinel",
            "-v",
            "ON_ERROR_STOP=1",
            "--set=restored_at=" + datetime.now(timezone.utc).isoformat(),
            input=RESTORE_POLICY,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        models = staging / "models"
        models.mkdir(exist_ok=True)
        # This helper mounts only the validated archive's model files read-only.
        # The application itself stays non-root and is not started by restore.
        install = """from pathlib import Path
import os, shutil
source=Path('/restore_models'); target=Path('/var/lib/cloudsentinel/models')
if target.exists() and any(target.iterdir()): raise SystemExit('Model destination must be empty')
shutil.copytree(source,target,dirs_exist_ok=True)
for file in [target,*target.rglob('*')]:
    os.chown(file,10001,10001)
    file.chmod(0o700 if file.is_dir() else 0o600)
"""
        compose(
            project,
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0",
            "-v",
            str(models) + ":/restore_models:ro",
            "worker",
            "python",
            "-c",
            install,
            capture_output=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--project", help="Fresh Compose project name for an offline restore.")
    args = parser.parse_args()
    try:
        if args.action == "backup":
            backup(args.archive, args.project)
            print("Private checksummed backup created. Store it securely; it is not encrypted.")
        else:
            restore(args.archive, args.project)
            print(
                "Restored offline. Sessions were revoked, automation paused, and pending email suppressed. Services were not started."
            )
    except Exception:
        raise SystemExit(
            "Backup/restore failed. Review Docker availability, archive integrity, storage, and the stopped/empty restore destination. No services were started."
        ) from None


if __name__ == "__main__":
    main()
