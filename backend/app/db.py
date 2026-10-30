"""Explicit local SQLite / shared PostgreSQL persistence boundary.

PostgreSQL is opt-in through KEDR_DATABASE_URL. No local records are copied.
The compatibility adapter retains the application's small SQLite SQL contract;
all PostgreSQL transaction contexts are serialized by an advisory transaction
lock so existing read/check/write admissions remain safe across app instances.
Keep computation and external requests outside these short transaction contexts.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import json
import math
import os
import sqlite3
import time
import uuid

from .postgres import PostgresConnection, connect_postgres


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def identifier() -> str:
    return uuid.uuid4().hex


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Database:
    def __init__(self, directory: str | Path, *, database_url: str | None = None):
        self.database_url = (os.environ.get("KEDR_DATABASE_URL", "") if database_url is None else database_url).strip()
        if self.database_url and not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("KEDR_DATABASE_URL must be a PostgreSQL connection URL.")
        self.backend = "postgresql" if self.database_url else "sqlite"
        self.directory = Path(directory).resolve()
        if self.backend == "sqlite":
            self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "platform.sqlite3"

    @contextmanager
    def connection(self):
        if self.backend == "postgresql":
            with connect_postgres(self.database_url) as raw:
                # The application previously relied on SQLite's single-writer
                # BEGIN IMMEDIATE semantics for quotas, versions and admission.
                # Acquire before reads too, so every context sees committed state.
                raw.execute("SET LOCAL lock_timeout = '15s'")
                raw.execute("SET LOCAL statement_timeout = '30s'")
                raw.execute("SELECT pg_advisory_xact_lock(1262830674, 1)")
                yield PostgresConnection(raw)
            return
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
        if self.backend == "postgresql":
            migrations = Path(__file__).resolve().parent.parent / "postgres_migrations"
            expected = {item.name for item in (migrations.parent / "migrations").glob("*.sql")}
            available = {item.name for item in migrations.glob("*.sql")}
            if not expected or expected != available:
                raise RuntimeError("PostgreSQL migration sources are missing or do not match the application schema versions.")
            # The connection-scoped transaction advisory lock also makes schema
            # initialization atomic across simultaneous cold starts / deploys.
            with self.connection() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
                for migration in sorted(migrations.glob("*.sql")):
                    if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (migration.name,)).fetchone():
                        continue
                    conn.executescript(migration.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations VALUES (?,?)", (migration.name, now()))
            return
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

    def record_auth_attempt(self, key: str, *, window_seconds: int = 300, limit: int = 30, clock: float | None = None) -> bool:
        """Atomically admit a shared authentication attempt, retaining no raw key.

        Hosted instances use the PostgreSQL server clock to avoid skew between
        function instances. ``clock`` is solely a deterministic-test override.
        Expired pseudonymous records are pruned on subsequent authentication
        attempts. Rejected attempts do not extend the existing rolling window.
        """
        if not isinstance(key, str) or not key or len(key) > 4096:
            raise ValueError("An authentication limiter key is required.")
        if not isinstance(window_seconds, int) or not 1 <= window_seconds <= 3600:
            raise ValueError("Authentication window must be between one and 3600 seconds.")
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Authentication attempt limit must be between one and 1000.")
        if clock is not None and not math.isfinite(clock):
            raise ValueError("Authentication limiter clock must be finite.")
        bucket = sha256(("kedr-auth-attempt-v1:" + key).encode("utf-8")).hexdigest()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if clock is None:
                stamp = float(conn.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp())").fetchone()[0]) if self.backend == "postgresql" else time.time()
            else:
                stamp = float(clock)
            conn.execute("DELETE FROM auth_attempts WHERE expires_at<=?", (stamp,))
            count = conn.execute("SELECT COUNT(*) FROM auth_attempts WHERE bucket_key=? AND attempted_at>?", (bucket, stamp - window_seconds)).fetchone()[0]
            if count >= limit:
                return False
            conn.execute("INSERT INTO auth_attempts VALUES (?,?,?,?)", (identifier(), bucket, stamp, stamp + window_seconds))
            return True
