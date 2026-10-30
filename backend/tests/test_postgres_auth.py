"""Atomic shared authentication admission against the dedicated test database."""
from concurrent.futures import ThreadPoolExecutor

from backend.app.db import Database
from backend.tests.test_postgres import pg_database  # noqa: F401 - shared isolated-schema fixture


def test_postgres_auth_attempt_cap_shared_across_instances(pg_database, tmp_path):
    instances = [Database(tmp_path / str(number), database_url=pg_database.database_url) for number in range(4)]

    def attempt(number):
        return instances[number % len(instances)].record_auth_attempt("192.0.2.50", clock=1000.0)

    with ThreadPoolExecutor(max_workers=12) as pool:
        accepted = list(pool.map(attempt, range(64)))
    assert sum(accepted) == 30
    assert not instances[-1].record_auth_attempt("192.0.2.50", clock=1001.0)
    assert instances[-1].record_auth_attempt("192.0.2.51", clock=1001.0)
    with pg_database.connection() as conn:
        rows = conn.execute("SELECT * FROM auth_attempts").fetchall()
        assert len(rows) == 31
        assert all(len(row["bucket_key"]) == 64 for row in rows)
        assert all("192.0.2" not in value for row in rows for value in (row["id"], row["bucket_key"]))
    # The original 30 attempts expire exactly at the rolling-window boundary.
    assert instances[0].record_auth_attempt("192.0.2.50", clock=1300.0)
    with pg_database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_attempts").fetchone()[0] == 2
    # Default production path must use the shared database server's current time.
    assert instances[1].record_auth_attempt("192.0.2.52")
    with pg_database.connection() as conn:
        row = conn.execute("SELECT attempted_at,EXTRACT(EPOCH FROM clock_timestamp()) AS server_time FROM auth_attempts").fetchone()
        assert abs(row[0] - float(row[1])) < 10
        assert conn.execute("SELECT COUNT(*) FROM auth_attempts").fetchone()[0] == 1
