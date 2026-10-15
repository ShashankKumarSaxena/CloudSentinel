"""Small DB-API boundary for local SQLite and deployed PostgreSQL.

Only trusted repository SQL crosses this boundary. SQL values always remain
bound parameters. Backend-specific schema changes live in versioned SQL files.
"""

import fcntl
from contextlib import contextmanager
from pathlib import Path
import sqlite3

MIGRATIONS = Path(__file__).parent / "migrations"
WORKER_LOCK = 43190721
WRITE_LOCK = 43190722


class Record(dict):
    """Keep named records while supporting DB-API count/tuple access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def postgres_row(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Record(zip(names, values))


class PostgresConnection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, statement, parameters=()):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            # Serialize short claim/admin transactions across API and workers.
            # The lock is transaction scoped and cannot survive a rollback/crash.
            return self.raw.execute("SELECT pg_advisory_xact_lock(%s)", (WRITE_LOCK,))
        return self.raw.execute(statement.replace("?", "%s"), parameters)

    def executemany(self, statement, parameters):
        cursor = self.raw.cursor()
        cursor.executemany(statement.replace("?", "%s"), parameters)
        return cursor


class WorkerLock:
    def __init__(self, handle):
        self.handle = handle

    def assert_owned(self):
        if self.handle is None or self.handle.closed:
            raise RuntimeError("Worker lock is closed.")
        if hasattr(self.handle, "execute"):
            self.handle.execute("SELECT 1")

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None


class Database:
    def __init__(self, path: Path, url: str | None = None):
        self.path, self.url = path, url
        self.postgres = url is not None
        if not self.postgres:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pool = None
        self.migrate()
        if self.postgres:
            from psycopg_pool import ConnectionPool

            self.pool = ConnectionPool(
                self.url,
                min_size=1,
                max_size=10,
                max_waiting=100,
                timeout=10,
                kwargs={"row_factory": postgres_row, "connect_timeout": 10},
                open=True,
            )
        if not self.postgres:
            path.chmod(0o600)

    def _postgres_connect(self, **kwargs):
        try:
            import psycopg
        except ImportError:
            raise RuntimeError(
                "Install backend/requirements-production.txt for PostgreSQL."
            ) from None
        try:
            return psycopg.connect(self.url, row_factory=postgres_row, connect_timeout=10, **kwargs)
        except Exception:
            raise RuntimeError(
                "PostgreSQL connection failed; review the private database configuration."
            ) from None

    @contextmanager
    def connection(self):
        if self.postgres:
            context = self.pool.connection() if self.pool else self._postgres_connect()
            with context as connection:
                yield PostgresConnection(connection)
            return
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self):
        if not self.postgres:
            with self.connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
            )
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
            }
            backend = "postgresql" if self.postgres else "sqlite"
            for file in sorted(MIGRATIONS.glob(f"*_{backend}.sql")):
                version = int(file.name.split("_")[0])
                if version in applied:
                    continue
                # Migration files use simple statements without embedded semicolons.
                # Run DDL/backfills together to avoid partially applied upgrades.
                for statement in file.read_text().split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute("INSERT INTO schema_migrations VALUES (?)", (version,))

    def lock_worker(self):
        if self.postgres:
            connection = self._postgres_connect(autocommit=True)
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s)", (WORKER_LOCK,)
            ).fetchone()[0]
            if not acquired:
                connection.close()
                raise RuntimeError("Another worker owns this workspace database.")
            return WorkerLock(connection)
        path = self.path.with_name(self.path.name + ".monitor.lock")
        handle = path.open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("Another worker owns this workspace database.") from None
        return WorkerLock(handle)

    def close(self):
        if self.pool:
            self.pool.close()
