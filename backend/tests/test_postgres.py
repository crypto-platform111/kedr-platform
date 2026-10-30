"""Opt-in real PostgreSQL persistence checks using disposable isolated schemas.

Set KEDR_TEST_POSTGRES_URL to a dedicated test database. This never reads a
developer's KEDR_DATABASE_URL or copies the installed local SQLite database.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import uuid

import pytest

from backend.app.db import Database, encode, now
from backend.app.postgres import CompatibleRow, translate_sql


def test_postgres_sql_contract_keeps_parameters_and_literals_separate():
    assert translate_sql("SELECT '?' AS x, id FROM users WHERE email=? COLLATE NOCASE") == "SELECT '?' AS x, id FROM users WHERE kedr_nocase(email)=kedr_nocase(%s)"
    assert translate_sql("SELECT MAX(number),MAX(accounted_tokens,?) FROM ai_usage") == "SELECT MAX(number),GREATEST(accounted_tokens,%s) FROM ai_usage"
    assert translate_sql("SELECT ? -- literal ?\n/* ? */ WHERE '?'='?' AND x LIKE 'a%'") == "SELECT %s -- literal ?\n/* ? */ WHERE '?'='?' AND x LIKE 'a%%'"
    row = CompatibleRow(["id", "value"], ["one", 2])
    assert row[0] == row["id"] == "one"
    assert row[1] == row["value"] == 2
    assert dict(row) == {"id": "one", "value": 2}


def test_postgres_configuration_is_opt_in_and_errors_do_not_echo_url(tmp_path, monkeypatch):
    monkeypatch.delenv("KEDR_DATABASE_URL", raising=False)
    local = Database(tmp_path)
    assert local.backend == "sqlite"
    local.initialize()
    assert local.path.is_file()
    with pytest.raises(ValueError, match="must be a PostgreSQL") as error:
        Database(tmp_path, database_url="invalid://private-value")
    assert "private-value" not in str(error.value)
    shared = Database(tmp_path / "uncreated", database_url="postgresql://localhost/example")
    assert shared.backend == "postgresql"
    assert not shared.directory.exists()


@pytest.fixture
def pg_database(tmp_path, monkeypatch):
    url = os.environ.get("KEDR_TEST_POSTGRES_URL", "").strip()
    if not url:
        pytest.skip("Set KEDR_TEST_POSTGRES_URL for a dedicated real PostgreSQL integration database")
    try:
        import psycopg
    except ImportError:
        pytest.fail("The explicit PostgreSQL integration test requires the pinned psycopg dependency")
    schema = "kedr_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "options"]
    query.append(("options", "-c search_path=" + schema))
    # libpq URI query values decode %20, not HTML form-style '+' spaces.
    isolated_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, quote_via=quote), parsed.fragment))
    monkeypatch.setenv("KEDR_DATABASE_URL", isolated_url)
    database = Database(tmp_path, database_url=isolated_url)
    try:
        database.initialize()
        yield database
    finally:
        # Drop only this fixture's random schema, never another schema or DB.
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(psycopg.sql.Identifier(schema)))


def user(database, value="owner"):
    with database.connection() as conn:
        conn.execute("INSERT INTO users (id,email,name,created_at) VALUES (?,?,?,?)", (value, value + "@example.invalid", "Test", now()))


def strategy_records(database):
    user(database)
    with database.connection() as conn:
        conn.execute("INSERT INTO strategies (id,owner_id,name,spec_json,created_at,updated_at) VALUES (?,?,?,?,?,?)", ("strategy", "owner", "Test", "{}", now(), now()))
        conn.execute("INSERT INTO strategy_versions VALUES (?,?,?,?,?,?)", ("version", "strategy", 1, "{}", "hash", now()))
        conn.execute("INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?)", ("run", "owner", "strategy", "version", "{}", "{}", "{}", "succeeded", now()))
        conn.execute("INSERT INTO publications (id,owner_id,strategy_id,version_id,run_id,name,author,description,tags_json,spec_json,dataset_json,metrics_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ("publication", "owner", "strategy", "version", "run", "Test", "Test", "Test", "[]", "{}", "{}", "{}", now()))


def test_postgres_migrations_idempotency_rows_and_case_insensitive_email(pg_database):
    database = pg_database
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: database.initialize(), range(4)))
    expected = len(list((Path(__file__).parents[1] / "postgres_migrations").glob("*.sql")))
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == expected
    user(database, "MixedCase")
    with database.connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", ("MIXEDCASE@EXAMPLE.INVALID",)).fetchone()
        assert row[0] == row["id"] == "MixedCase"
        assert dict(row)["email"] == "MixedCase@example.invalid"
        with pytest.raises(sqlite3.IntegrityError, match="unique"):
            conn.execute("INSERT INTO users (id,email,name,created_at) VALUES (?,?,?,?)", ("two", "mixedcase@example.invalid", "Test", now()))
        # A caught failed statement must not poison the rest of the transaction.
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="foreign key"):
            conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", ("token", "missing", "csrf", 1234, now()))


def test_postgres_transaction_rollback_and_cross_connection_visibility(pg_database):
    database = pg_database
    with pytest.raises(RuntimeError, match="abort test"):
        with database.connection() as conn:
            conn.execute("INSERT INTO users (id,email,name,created_at) VALUES (?,?,?,?)", ("rolled-back", "rollback@example.invalid", "Test", now()))
            raise RuntimeError("abort test")
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    user(database)
    other_instance = Database(database.directory, database_url=database.database_url)
    with other_instance.connection() as conn:
        assert conn.execute("SELECT id FROM users").fetchone()[0] == "owner"


def test_postgres_immutable_triggers_and_json_constraints(pg_database):
    strategy_records(pg_database)
    with pg_database.connection() as conn:
        for table in ("strategy_versions", "backtests", "publications"):
            for statement in (f"UPDATE {table} SET id=id", f"DELETE FROM {table}"):
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    conn.execute(statement)
        with pytest.raises(sqlite3.IntegrityError, match="check"):
            conn.execute("INSERT INTO dataset_references VALUES (?,?,?,?,?,?,?,?)", ("dataset", "test", "BTCUSDT", "1d", "synthetic_demo", "hash", "not json", now()))
        conn.execute("INSERT INTO dataset_references VALUES (?,?,?,?,?,?,?,?)", ("dataset", "test", "BTCUSDT", "1d", "synthetic_demo", "hash", encode({"valid": True}), now()))
        conn.execute("INSERT INTO research_jobs (id,owner_id,kind,name,status,configuration_json,created_at) VALUES (?,?,?,?,?,?,?)", ("research", "owner", "ml", "Test", "succeeded", "{}", now()))
        conn.execute("INSERT INTO model_registry VALUES (?,?,?,?,?,?,?)", ("model", "owner", "research", "test", "{}", "hash", now()))
        for statement in ("UPDATE model_registry SET id=id", "DELETE FROM model_registry"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(statement)
        conn.execute("INSERT INTO copilot_conversations VALUES (?,?,?,?,?,?)", ("conversation", "owner", "strategy", "Test", "en", now()))
        conn.execute("INSERT INTO copilot_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("proposal", "owner", "conversation", "strategy", "{}", "hash", "{}", "hash", "[]", "{}", "pending", None, now(), None))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE copilot_proposals SET proposed_spec_json='{}' WHERE id='proposal'")
        assert conn.execute("UPDATE copilot_proposals SET status='rejected' WHERE id='proposal'").rowcount == 1


def test_postgres_insertion_order_and_scalar_max(pg_database):
    strategy_records(pg_database)
    with pg_database.connection() as conn:
        conn.execute("INSERT INTO copilot_conversations VALUES (?,?,?,?,?,?)", ("conversation", "owner", "strategy", "Test", "en", now()))
        for mid in ("z-message", "a-message"):
            conn.execute("INSERT INTO copilot_messages VALUES (?,?,?,?,?,?,?,?)", (mid, "conversation", "user", mid, "user", "[]", "{}", "same-clock"))
        assert [row[0] for row in conn.execute("SELECT id FROM copilot_messages ORDER BY rowid")] == ["z-message", "a-message"]
        conn.execute("INSERT INTO ai_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("usage", "owner", "2026-01-01", "reserved", 10, 10, .1, .1, "test", "test", "{}", now()))
        conn.execute("UPDATE ai_usage SET accounted_tokens=MAX(accounted_tokens,?),accounted_usd=MAX(accounted_usd,?) WHERE id=?", (20, .2, "usage"))
        row = conn.execute("SELECT accounted_tokens,accounted_usd FROM ai_usage").fetchone()
        assert row[0] == 20 and row[1] == .2


def test_postgres_serialized_admission_prevents_count_insert_race(pg_database):
    user(pg_database)

    def admit(number):
        with pg_database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT COUNT(*) FROM chart_preferences WHERE owner_id=?", ("owner",)).fetchone()[0] >= 1:
                return False
            conn.execute("INSERT INTO chart_preferences VALUES (?,?,?,?)", ("owner", str(number), "{}", now()))
            return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(admit, range(8)))
    assert sum(outcomes) == 1
    with pg_database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chart_preferences").fetchone()[0] == 1


def test_postgres_api_auth_strategy_backtest_and_shared_session(pg_database, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("KEDR_JOB_MODE", "local")
    monkeypatch.setenv("KEDR_SECURE_COOKIES", "0")
    app = create_app(tmp_path / "instance-one")
    with TestClient(app) as client:
        response = client.post("/api/auth/register", json={"email": "postgres-api@example.invalid", "password": "TestFixturePassword123!", "name": "PostgreSQL fixture"})
        assert response.status_code == 201, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert client.post("/api/auth/login", json={"email": "POSTGRES-API@example.invalid", "password": "TestFixturePassword123!"}).status_code == 200
        client.headers["X-CSRF-Token"] = client.get("/api/auth/me").json()["csrf_token"]
        spec = client.get("/api/templates").json()[0]["spec"]
        saved = client.post("/api/strategies", json={"name": "PG integration", "spec": spec})
        assert saved.status_code == 201, saved.text
        saved = saved.json()
        version = client.post(f"/api/strategies/{saved['id']}/versions")
        assert version.status_code == 201, version.text
        queued = client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"start": "2023-01-01", "end": "2023-12-31"}})
        assert queued.status_code == 202, queued.text
        jid = queued.json()["id"]
        for _ in range(500):
            job = client.get("/api/jobs/" + jid).json()
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(.02)
        assert job["status"] == "succeeded", job
        assert client.get("/api/backtests/" + job["run_id"]).status_code == 200
        with TestClient(create_app(tmp_path / "instance-two")) as other:
            other.cookies.update(client.cookies)
            assert other.get("/api/auth/me").status_code == 200
            assert other.get("/api/strategies/" + saved["id"]).json()["name"] == "PG integration"
            assert other.get("/api/backtests/" + job["run_id"]).status_code == 200
        assert not (tmp_path / "instance-one" / "platform.sqlite3").exists()
        assert not (tmp_path / "instance-two" / "platform.sqlite3").exists()
