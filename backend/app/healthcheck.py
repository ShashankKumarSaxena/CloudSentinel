"""Container health probes without application startup or model initialization."""

from datetime import datetime, timedelta, timezone
from urllib.request import urlopen
import sys

from backend.app.core.config import Settings


def main():
    if sys.argv[1:] != ["worker"]:
        with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=3) as response:
            if response.status != 200:
                raise SystemExit(1)
        return
    try:
        settings = Settings.from_env()
        if settings.database_url:
            import psycopg

            with psycopg.connect(
                settings.database_url.get_secret_value(), connect_timeout=3
            ) as connection:
                row = connection.execute(
                    "SELECT updated_at,status FROM worker_heartbeat WHERE id=1"
                ).fetchone()
        else:
            import sqlite3

            with sqlite3.connect(settings.database_path, timeout=3) as connection:
                row = connection.execute(
                    "SELECT updated_at,status FROM worker_heartbeat WHERE id=1"
                ).fetchone()
        valid = (
            row
            and row[1] == "running"
            and datetime.fromisoformat(row[0])
            > datetime.now(timezone.utc) - timedelta(seconds=settings.worker_stale_seconds)
        )
    except Exception:
        valid = False
    raise SystemExit(0 if valid else 1)


if __name__ == "__main__":
    main()
