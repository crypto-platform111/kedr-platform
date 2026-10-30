"""Opt-in real PostgreSQL durability checks, with a fresh schema per test.

Only the queue transport is substituted. Persisted claims, transactions,
concurrent completion and a real synthetic-data backtest use PostgreSQL.
No installed application database or private research data enters these tests.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import threading

import pytest

from backend.app.db import Database, encode, identifier, now
from backend.app.domain import templates
from backend.app.durable_jobs import DurableJobs, WorkBusy
from backend.tests import test_durable_jobs as cases
from backend.tests.test_postgres import pg_database  # noqa: F401 -- pytest fixture


@pytest.fixture
def pg_stored(pg_database):
    database = pg_database
    assert database.backend == "postgresql"
    owner, strategy, version = identifier(), identifier(), identifier()
    spec = next(item["spec"] for item in templates() if item["id"] == "buy_hold")
    with database.connection() as conn:
        conn.execute("INSERT INTO users (id,email,name,created_at) VALUES (?,?,?,?)", (owner, "durable-pg-fixture@example.invalid", "Fixture", now()))
        conn.execute("INSERT INTO strategies (id,owner_id,name,spec_json,created_at,updated_at) VALUES (?,?,?,?,?,?)", (strategy, owner, "Fixture", encode(spec), now(), now()))
        conn.execute("INSERT INTO strategy_versions VALUES (?,?,?,?,?,?)", (version, strategy, 1, encode(spec), sha256(encode(spec).encode()).hexdigest(), now()))
    return database, owner, strategy, version, spec


def test_postgres_job_and_outbox_roll_back_together(pg_stored):
    cases.test_job_and_outbox_are_one_atomic_transaction(pg_stored)


def test_postgres_two_instances_claim_and_complete_exactly_once(pg_stored):
    database = pg_stored[0]
    other_database = Database(database.directory, database_url=database.database_url)
    first, second = DurableJobs(database), DurableJobs(other_database)
    key, job, _ = cases.backtest(pg_stored, first)
    barrier = threading.Barrier(2)

    def claim(service):
        barrier.wait(timeout=10)
        try:
            return service.claim(key)
        except WorkBusy:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, (first, second)))
    assert sum(claim is not None for claim in claims) == 1
    winner = next(claim for claim in claims if claim is not None)
    output = first._compute(winner)
    barrier = threading.Barrier(2)

    def complete(service):
        barrier.wait(timeout=10)
        return service.complete(winner, output)

    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = list(pool.map(complete, (first, second)))
    assert sorted(completed) == [False, True]
    assert asyncio.run(second.handle(key)) == "already_terminal"
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='backtest.completed'").fetchone()[0] == 1
    assert cases.row(database, "jobs", job)["status"] == "succeeded"


def test_postgres_expired_instance_is_fenced_after_other_instance_reclaims(pg_stored):
    database, clock = pg_stored[0], cases.Clock()
    other_database = Database(database.directory, database_url=database.database_url)
    first = DurableJobs(database, clock=clock)
    second = DurableJobs(other_database, clock=clock)
    key, job, _ = cases.backtest(pg_stored, first)
    old = first.claim(key)
    output = first._compute(old)
    clock.advance(601)
    new = second.claim(key)
    assert new.token != old.token and new.attempt == 2
    assert not first.complete(old, output)
    assert second.complete(new, output)
    assert cases.row(database, "jobs", job)["status"] == "succeeded"
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0] == 1


def test_postgres_cancel_suppresses_result_and_model_artifact(pg_stored):
    cases.test_cancel_during_computation_suppresses_artifact_and_late_completion(pg_stored)


def test_postgres_queue_outage_keeps_recoverable_outbox_without_secret_logs(pg_stored, caplog):
    cases.test_failed_queue_send_remains_recoverable_and_never_logs_transport_secret(pg_stored, caplog)


def test_postgres_real_backtest_saved_result_and_replay_match(pg_stored):
    cases.test_real_backtest_saved_output_and_request_bound_replay_match_engine_hash(pg_stored)


def test_postgres_ml_registry_result_and_audit_commit_once(pg_stored):
    cases.test_ml_registry_and_result_complete_atomically_exactly_once(pg_stored)


def test_postgres_expired_delivery_recovers_without_stealing_live_lease(pg_stored):
    cases.test_recovery_dispatches_expired_claim_but_not_live_claim(pg_stored)


def test_postgres_fixed_retries_end_in_terminal_failure(pg_stored):
    cases.test_fixed_retry_budget_delayed_retry_and_terminal_failure(pg_stored)
