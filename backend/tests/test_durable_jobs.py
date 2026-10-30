"""Durable delivery tests use real isolated DB transactions and real engines.

Only queue transport is substituted: no provider, private dataset or cloud
account is required. Lost acknowledgements, cancellation and process death are
represented at the exact persisted claim/completion boundary.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from backend.app import data, engine
from backend.app.db import Database, encode, identifier, now
from backend.app.domain import templates
from backend.app.durable_jobs import DurableJobs, MAX_ATTEMPTS, WorkBusy


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def stored(tmp_path):
    db = Database(tmp_path)
    db.initialize()
    owner, sid, vid = identifier(), identifier(), identifier()
    spec = next(t["spec"] for t in templates() if t["id"] == "buy_hold")
    with db.connection() as conn:
        conn.execute("INSERT INTO users (id,email,name,created_at) VALUES (?,?,?,?)", (owner, "durable-fixture@example.invalid", "Fixture", now()))
        conn.execute("INSERT INTO strategies (id,owner_id,name,spec_json,created_at,updated_at) VALUES (?,?,?,?,?,?)", (sid, owner, "Fixture", encode(spec), now(), now()))
        conn.execute("INSERT INTO strategy_versions VALUES (?,?,?,?,?,?)", (vid, sid, 1, encode(spec), sha256(encode(spec).encode()).hexdigest(), now()))
    return db, owner, sid, vid, spec


def backtest(stored, service):
    db, owner, sid, vid, _ = stored
    jid = identifier()
    config = {"start": "2023-01-01", "end": "2023-12-31", "initial_cash": 1000, "fee_bps": 10, "slippage_bps": 2, "execution_delay_bars": 1}
    with db.connection() as conn:
        conn.execute("INSERT INTO jobs (id,owner_id,strategy_id,version_id,dataset_id,config_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)", (jid, owner, sid, vid, "demo_btc_4h", encode(config), "queued", now()))
        key = service.enqueue(conn, "backtest", jid, owner)
    return key, jid, config


def research_job(stored, service, kind="ml"):
    db, owner, _, _, spec = stored
    jid = identifier()
    config = {"dataset_id": "demo_btc_4h", "name": "Fixture", "target": "direction", "model_family": "logistic", "horizon_bars": 6,
              "feature_groups": ["momentum", "volatility", "calendar"], "start": "2022-01-01", "end": "2025-12-31"}
    if kind == "scenarios":
        config = {"spec": spec, "dataset_id": "demo_btc_4h", "scenario_kind": "costs",
                  "config": {"start": "2023-01-01", "end": "2023-12-31", "initial_cash": 1000, "fee_bps": 10, "slippage_bps": 2, "execution_delay_bars": 1}}
    with db.connection() as conn:
        conn.execute("INSERT INTO research_jobs (id,owner_id,kind,name,status,configuration_json,created_at) VALUES (?,?,?,?,?,?,?)", (jid, owner, kind, "Fixture", "queued", encode(config), now()))
        key = service.enqueue(conn, "research", jid, owner)
    return key, jid


def row(db, table, key, field="id"):
    assert table in ("jobs", "research_jobs", "durable_work")
    assert field in ("id", "work_key")
    with db.connection() as conn:
        return dict(conn.execute(f"SELECT * FROM {table} WHERE {field}=?", (key,)).fetchone())


def test_job_and_outbox_are_one_atomic_transaction(stored):
    db, owner, sid, vid, _ = stored
    service, jid = DurableJobs(db), identifier()
    with pytest.raises(RuntimeError):
        with db.connection() as conn:
            conn.execute("INSERT INTO jobs (id,owner_id,strategy_id,version_id,dataset_id,config_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)", (jid, owner, sid, vid, "demo_btc_4h", "{}", "queued", now()))
            service.enqueue(conn, "backtest", jid, owner)
            raise RuntimeError("transaction aborted before admission")
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM durable_work").fetchone()[0] == 0


def test_failed_queue_send_remains_recoverable_and_never_logs_transport_secret(stored, caplog):
    db = stored[0]
    received = []

    async def unavailable(payload, key):
        raise RuntimeError("Authorization: secret-fixture-do-not-log")

    service = DurableJobs(db, publisher=unavailable)
    key, jid, _ = backtest(stored, service)
    assert service.dispatch_pending_sync() == {"published": 0, "deferred": 1}
    assert row(db, "jobs", jid)["status"] == "queued"
    assert row(db, "durable_work", key, "work_key")["outbox_pending"] == 1
    assert "secret-fixture-do-not-log" not in caplog.text

    async def available(payload, idempotency_key):
        received.append((payload, idempotency_key))
        return None  # The real SDK defines this as accepted deferred ingestion.

    service.publisher = available
    assert service.dispatch_pending_sync() == {"published": 1, "deferred": 0}
    assert received == [({"work_key": key}, key + ":2")]
    assert row(db, "durable_work", key, "work_key")["outbox_pending"] == 0


def test_two_instances_claim_once_and_duplicate_delivery_has_no_second_saved_run(stored):
    db = stored[0]
    first, second = DurableJobs(db), DurableJobs(db)
    key, jid, _ = backtest(stored, first)
    barrier = threading.Barrier(2)

    def claim(service):
        barrier.wait(timeout=5)
        try:
            return service.claim(key)
        except WorkBusy:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, (first, second)))
    claim = next(c for c in claims if c is not None)
    assert sum(c is not None for c in claims) == 1
    output = first._compute(claim)
    assert first.complete(claim, output)
    assert not second.complete(claim, output)
    assert asyncio.run(second.handle(key)) == "already_terminal"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='backtest.completed'").fetchone()[0] == 1
    assert row(db, "jobs", jid)["status"] == "succeeded"


def test_expired_worker_cannot_commit_after_new_instance_reclaims(stored):
    db, clock = stored[0], Clock()
    first, second = DurableJobs(db, clock=clock), DurableJobs(db, clock=clock)
    key, jid, _ = backtest(stored, first)
    old = first.claim(key)
    output = first._compute(old)
    clock.advance(601)
    new = second.claim(key)
    assert new.token != old.token and new.attempt == 2
    assert not first.complete(old, output)
    assert second.complete(new, output)
    assert row(db, "jobs", jid)["status"] == "succeeded"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0] == 1


def test_cancel_during_computation_suppresses_artifact_and_late_completion(stored):
    db = stored[0]
    service = DurableJobs(db)
    key, jid = research_job(stored, service)
    claim = service.claim(key)
    with db.connection() as conn:
        conn.execute("UPDATE research_jobs SET status='cancelled',finished_at=? WHERE id=?", (now(), jid))
    assert not service.complete(claim, {"result": {"artifact": {"weights": [1, 2]}}})
    assert row(db, "durable_work", key, "work_key")["status"] == "cancelled"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0] == 0


def test_fixed_retry_budget_delayed_retry_and_terminal_failure(stored):
    db, clock = stored[0], Clock()

    def interrupted(_):
        raise RuntimeError("Transport disappeared")

    service = DurableJobs(db, clock=clock, compute=interrupted)
    key, jid, _ = backtest(stored, service)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt < MAX_ATTEMPTS:
            with pytest.raises(WorkBusy):
                asyncio.run(service.handle(key))
            with pytest.raises(WorkBusy):
                service.claim(key)
            assert row(db, "durable_work", key, "work_key")["attempt"] == attempt
        else:
            assert asyncio.run(service.handle(key)) == "failed"
        clock.advance(301)
    assert row(db, "jobs", jid)["status"] == "failed"
    assert row(db, "durable_work", key, "work_key")["outbox_pending"] == 0


def test_last_attempt_process_death_eventually_fails_instead_of_sticking(stored):
    db, clock = stored[0], Clock()
    service = DurableJobs(db, clock=clock)
    key, jid, _ = backtest(stored, service)
    for _ in range(MAX_ATTEMPTS):
        assert service.claim(key) is not None
        clock.advance(601)
    assert service.claim(key) is None
    assert row(db, "jobs", jid)["status"] == "failed"


def test_recovery_dispatches_expired_claim_but_not_live_claim(stored):
    db, clock, sent = stored[0], Clock(), []

    async def publish(payload, key):
        sent.append((payload, key))
        return "queue-message"

    service = DurableJobs(db, clock=clock, publisher=publish)
    key, _, _ = backtest(stored, service)
    assert service.dispatch_pending_sync()["published"] == 1
    service.claim(key)
    clock.advance(300)
    assert service.dispatch_pending_sync()["published"] == 0
    clock.advance(301)
    assert service.dispatch_pending_sync()["published"] == 1
    assert sent == [({"work_key": key}, key + ":1"), ({"work_key": key}, key + ":2")]


def test_real_backtest_saved_output_and_request_bound_replay_match_engine_hash(stored):
    db, _, _, _, spec = stored
    service = DurableJobs(db)
    key, jid, config = backtest(stored, service)
    expected = encode(engine.run_backtest(spec, data.load_dataset_for_strategy(spec, "demo_btc_4h"), config))
    assert asyncio.run(service.handle(key)) == "succeeded"
    run_id = row(db, "jobs", jid)["run_id"]
    with db.connection() as conn:
        saved = conn.execute("SELECT result_json FROM backtests WHERE id=?", (run_id,)).fetchone()[0]
    assert sha256(saved.encode()).hexdigest() == sha256(expected.encode()).hexdigest()
    assert encode(service.reproduce(spec, "demo_btc_4h", config)) == expected


def test_ml_registry_and_result_complete_atomically_exactly_once(stored):
    db = stored[0]
    artifact = {"schema_version": 1, "weights": [0.1, 0.2], "feature_names": ["a", "b"]}
    service = DurableJobs(db, compute=lambda _: {"result": {"artifact": artifact, "metric": .5}})
    key, jid = research_job(stored, service)
    assert asyncio.run(service.handle(key)) == "succeeded"
    assert asyncio.run(service.handle(key)) == "already_terminal"
    with db.connection() as conn:
        models = list(conn.execute("SELECT * FROM model_registry"))
        assert len(models) == 1
        assert models[0]["artifact_json"] == encode(artifact)
        assert models[0]["artifact_sha256"] == sha256(encode(artifact).encode()).hexdigest()
        result = json.loads(conn.execute("SELECT result_json FROM research_jobs WHERE id=?", (jid,)).fetchone()[0])
        assert result["model_id"] == models[0]["id"]
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='research.completed'").fetchone()[0] == 1


def test_registry_and_job_completion_roll_back_if_final_audit_write_fails(stored, monkeypatch):
    db = stored[0]
    service = DurableJobs(db)
    key, jid = research_job(stored, service)
    claim = service.claim(key)

    def unavailable_audit(*args, **kwargs):
        raise RuntimeError("simulated connection failure before commit")

    monkeypatch.setattr(db, "audit", unavailable_audit)
    with pytest.raises(RuntimeError):
        service.complete(claim, {"result": {"artifact": {"weights": [1, 2]}}})
    assert row(db, "research_jobs", jid)["status"] == "running"
    assert row(db, "durable_work", key, "work_key")["status"] == "running"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0] == 0


def test_oversized_research_result_saves_no_partial_model(stored):
    db = stored[0]
    service = DurableJobs(db, compute=lambda _: {"result": {"artifact": {"padding": "x" * 3_000_001}}})
    key, jid = research_job(stored, service)
    assert asyncio.run(service.handle(key)) == "failed"
    assert row(db, "research_jobs", jid)["result_json"] is None
    assert row(db, "research_jobs", jid)["status"] == "failed"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0] == 0


def test_real_fixed_scenario_engine_runs_in_invocation(stored):
    db = stored[0]
    service = DurableJobs(db)
    key, jid = research_job(stored, service, "scenarios")
    assert asyncio.run(service.handle(key)) == "succeeded"
    result = json.loads(row(db, "research_jobs", jid)["result_json"])
    assert [arm["name"] for arm in result["arms"]] == ["half_cost", "base_cost", "double_cost"]
    assert not result["selection_performed"]
    assert not result["model_refitting"]


def test_real_bounded_ml_process_finishes_before_queue_handler_returns(stored):
    db = stored[0]
    service = DurableJobs(db)
    key, jid = research_job(stored, service)
    assert asyncio.run(service.handle(key)) == "succeeded"
    result = json.loads(row(db, "research_jobs", jid)["result_json"])
    assert result["resources"]["separate_process"]
    assert result["resources"]["worker_pid"] != os.getpid()
    assert result["resources"]["memory_limit_mib"] == 256
    assert result["reload_max_error"] == 0
    assert result["metrics"]["test"]["n"] >= 20
    assert result["baseline_metrics"]["test"]["n"] == result["metrics"]["test"]["n"]
    assert not result["artifact"]["strategy_node_executable"]
    assert not service.runner.processes
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0] == 1


def test_permanent_input_failure_is_not_retried(stored):
    db = stored[0]

    def invalid(_):
        raise ValueError("invalid provider path C:/private-fixture")

    service = DurableJobs(db, compute=invalid)
    key, jid, _ = backtest(stored, service)
    assert asyncio.run(service.handle(key)) == "failed"
    assert row(db, "jobs", jid)["error"] == "Hosted execution failed its input/resource checks."
    assert row(db, "durable_work", key, "work_key")["attempt"] == 1


def test_sdk_subscriber_discovery_never_constructs_database_or_calls_network(tmp_path):
    script = """
import socket
from backend.app import db
def forbidden(*args, **kwargs):
    raise AssertionError('Discovery attempted a database or network operation')
db.Database.__init__ = forbidden
socket.create_connection = forbidden
import backend.app.queue_bridge as bridge
from vercel.queue import get_subscriptions
items = [s for s in get_subscriptions() if s.func is bridge.process_work]
assert len(items) == 1
sub = items[0]
assert sub.topic == 'kedr-research-work'
assert sub.consumer_group == 'kedr-work-v1'
assert sub.retry_after_seconds == 60
assert sub.max_concurrency == 2
assert sub.max_attempts == 20
print('private subscriber discovery passed')
"""
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment.update(KEDR_LEGACY_ROOT="", KEDR_DATA_DIR=str(tmp_path / "unused"), KEDR_AI_PROVIDER="disabled",
                       KEDR_DATABASE_URL="postgresql://discovery-fixture.invalid/unused")
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "private subscriber discovery passed"
    assert not (tmp_path / "unused").exists()


def test_queue_publisher_uses_real_sdk_contract_with_no_identity_or_input_payload(monkeypatch):
    from vercel import queue
    from backend.app.durable_jobs import QueuePublisher, TOPIC

    sent = []

    async def send(topic, payload, **kwargs):
        sent.append((topic, payload, kwargs))
        return "opaque-queue-message"

    monkeypatch.setattr(queue, "send", send)
    key = "backtest:" + "a" * 32
    assert asyncio.run(QueuePublisher()({"work_key": key}, key + ":1")) == "opaque-queue-message"
    assert sent == [(TOPIC, {"work_key": key}, {"idempotency_key": key + ":1", "retention": 86400})]


def _sdk_message(payload):
    from vercel.queue import Message, MessageMetadata

    return Message(payload=payload, metadata=MessageMetadata(
        message_id="opaque-fixture-message", delivery_count=1, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        topic="kedr-research-work", consumer_group="kedr-work-v1",
    ))


def test_real_sdk_bridge_processes_saved_work_without_external_queue_publish(stored, monkeypatch):
    from backend.app import db as db_module, queue_bridge

    db = stored[0]
    service = DurableJobs(db)
    key, jid, _ = backtest(stored, service)
    constructed = []

    def database(directory, **kwargs):
        constructed.append((directory, kwargs))
        return db

    monkeypatch.setenv("KEDR_DATABASE_URL", "postgresql://bridge-fixture.invalid/database")
    monkeypatch.setattr(db_module, "Database", database)
    asyncio.run(queue_bridge.process_work(_sdk_message({"work_key": key})))
    assert constructed == [("/tmp/kedr", {"database_url": "postgresql://bridge-fixture.invalid/database"})]
    assert row(db, "jobs", jid)["status"] == "succeeded"


def test_real_sdk_bridge_busy_delivery_requests_retry_and_missing_database_fails(stored, monkeypatch):
    from backend.app import db as db_module, queue_bridge
    from vercel.queue import RetryAfter

    db = stored[0]
    service = DurableJobs(db)
    key, _, _ = backtest(stored, service)
    service.claim(key)
    monkeypatch.setenv("KEDR_DATABASE_URL", "postgresql://bridge-fixture.invalid/database")
    monkeypatch.setattr(db_module, "Database", lambda *args, **kwargs: db)
    with pytest.raises(RetryAfter) as retry:
        asyncio.run(queue_bridge.process_work(_sdk_message({"work_key": key})))
    assert retry.value.timeout_seconds == 60
    monkeypatch.delenv("KEDR_DATABASE_URL")
    with pytest.raises(RuntimeError, match="configured shared database"):
        asyncio.run(queue_bridge.process_work(_sdk_message({"work_key": key})))


@pytest.mark.parametrize("payload", [{}, {"work_key": "https://untrusted.invalid"}, {"work_key": "backtest:" + "a" * 32, "extra": "unexpected"}])
def test_real_sdk_bridge_rejects_non_reference_payloads_before_database(payload, monkeypatch):
    from backend.app import db as db_module, queue_bridge

    def forbidden(*args, **kwargs):
        pytest.fail("Malformed delivery reached the database")

    monkeypatch.setattr(db_module, "Database", forbidden)
    with pytest.raises(ValueError, match="Invalid durable work reference"):
        asyncio.run(queue_bridge.process_work(_sdk_message(payload)))


def test_awaited_worker_keeps_event_loop_alive_and_never_returns_before_completion(stored):
    db = stored[0]
    entered, release = threading.Event(), threading.Event()
    compute_thread = []

    def synchronous_compute(_):
        compute_thread.append(threading.get_ident())
        entered.set()
        if not release.wait(timeout=3):
            raise RuntimeError("Event-loop heartbeat could not release the worker")
        return {"result": {"fixture": "completed"}, "dataset": {"id": "synthetic-thread-fixture"}}

    service = DurableJobs(db, compute=synchronous_compute)
    key, jid, _ = backtest(stored, service)

    async def verify():
        task = asyncio.create_task(service.handle(key))
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(.01)
        assert entered.is_set()
        assert len(compute_thread) == 1 and compute_thread[0] != threading.get_ident()
        assert not task.done()
        heartbeats = 0
        for _ in range(3):
            await asyncio.sleep(.01)
            heartbeats += 1
            assert not task.done()
        assert heartbeats == 3
        assert row(db, "jobs", jid)["status"] == "running"
        release.set()
        assert await asyncio.wait_for(task, timeout=3) == "succeeded"
        assert row(db, "jobs", jid)["status"] == "succeeded"

    try:
        asyncio.run(verify())
    finally:
        release.set()


def test_async_injected_compute_still_runs_on_event_loop(stored):
    db = stored[0]
    threads = []

    async def compute(_):
        threads.append(threading.get_ident())
        await asyncio.sleep(0)
        return {"result": {"fixture": "completed"}, "dataset": {"id": "synthetic-async-fixture"}}

    service = DurableJobs(db, compute=compute)
    key, _, _ = backtest(stored, service)

    async def verify():
        assert await service.handle(key) == "succeeded"
        assert threads == [threading.get_ident()]

    asyncio.run(verify())
