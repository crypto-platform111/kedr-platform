"""Small, explicit SQLite persistence boundary for the isolated local platform."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def identifier() -> str:
    return uuid.uuid4().hex


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Database:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "platform.sqlite3"

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        migrations = Path(__file__).resolve().parent.parent / "migrations"
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            for migration in sorted(migrations.glob("*.sql")):
                if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (migration.name,)).fetchone():
                    continue
                # Each migration and its registration are one SQLite transaction.
                sql = migration.read_text(encoding="utf-8")
                stamp = now().replace("'", "''")
                version = migration.name.replace("'", "''")
                conn.executescript("BEGIN IMMEDIATE;\n" + sql + f"\nINSERT INTO schema_migrations VALUES ('{version}','{stamp}');\nCOMMIT;")

    def audit(self, conn, owner_id: str, action: str, entity_id: str | None = None, details=None):
        conn.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?)", (identifier(), owner_id, action, entity_id, encode(details or {}), now()))
