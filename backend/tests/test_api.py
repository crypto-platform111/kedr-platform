"""Real SQLite/API integration tests; simulated data is explicit and isolated."""
from copy import deepcopy
import asyncio
import json
import sqlite3
import threading
import time

from fastapi.testclient import TestClient
import pytest

from backend.app.main import create_app
from backend.app import main


@pytest.fixture
def running(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        yield app, client, tmp_path


def demo(client):
    response = client.post("/api/auth/demo", json={})
    assert response.status_code == 200, response.text
    payload = response.json()
    client.headers["X-CSRF-Token"] = payload["csrf_token"]
    return payload


def strategy(client, name="Integration strategy"):
    spec = deepcopy(client.get("/api/templates").json()[0]["spec"])
    result = client.post("/api/strategies", json={"name": name, "spec": spec, "description": "A private test draft", "tags": ["test"]})
    assert result.status_code == 201, result.text
    return result.json()


def completed(client, saved):
    response = client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"start": "2023-01-01", "end": "2023-12-31"}})
    assert response.status_code == 202, response.text
    job = response.json()
    for _ in range(500):
        job = client.get("/api/jobs/" + job["id"]).json()
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(.02)
    assert job["status"] == "succeeded", job
    result = client.get("/api/backtests/" + job["run_id"])
    assert result.status_code == 200
    return job, result.json()


def test_auth_hashes_cookie_csrf_logout_and_profile(running):
    app, client, directory = running
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/api/auth/register", json={"email": "test@example.com", "password": "TestPassword123!", "name": "Тест"})
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    auth = response.json()
    with app.state.db.connection() as conn:
        row = conn.execute("SELECT * FROM users").fetchone()
        assert row["password_hash"].startswith("scrypt$16384$8$1$")
        assert "TestPassword" not in row["password_hash"]
        assert conn.execute("SELECT token_hash FROM sessions").fetchone()[0] != client.cookies.get("kedr_session")
    assert client.patch("/api/profile", json={"locale": "en"}).status_code == 403
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
    assert client.patch("/api/profile", json={"locale": "en", "timezone": "Europe/Minsk", "level": "advanced"}).json()["locale"] == "en"
    assert client.patch("/api/profile", json={"timezone": "Invented/Zone"}).status_code == 422
    assert client.patch("/api/profile", json={"is_demo": False}).status_code == 422
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "TEST@example.com", "password": "TestPassword123!"}).status_code == 200


def test_demo_identities_and_private_resources_are_isolated(running):
    app, client, _ = running
    alice = demo(client)
    saved = strategy(client)
    job, run = completed(client, saved)
    second = TestClient(app)
    bob = demo(second)
    assert bob["user"]["id"] != alice["user"]["id"]
    assert second.get("/api/strategies").json() == []
    for route in (f"/api/strategies/{saved['id']}", f"/api/strategies/{saved['id']}/versions", f"/api/jobs/{job['id']}", f"/api/backtests/{run['id']}", f"/api/backtests/{run['id']}/analysis"):
        assert second.get(route).status_code == 404, route
    assert second.put("/api/strategies/" + saved["id"], json={"name": "stolen", "spec": saved["spec"]}).status_code == 404
    assert second.delete("/api/strategies/" + saved["id"]).status_code == 404
    assert second.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h"}).status_code == 404
    assert second.post("/api/community", json={"strategy_id": saved["id"], "version_id": run["version_id"], "run_id": run["id"]}).status_code == 404
    audit = second.get("/api/audit").json()
    assert all(event["action"] == "auth.demo_created" for event in audit)


def test_versions_jobs_and_publication_retain_exact_snapshots(running):
    app, client, _ = running
    demo(client)
    saved = strategy(client)
    original = deepcopy(saved["spec"])
    original_version = saved["latest_version_id"]
    changed = deepcopy(original)
    changed["risk"]["max_exposure"] = .5
    response = client.put("/api/strategies/" + saved["id"], json={"name": "Changed draft", "spec": changed})
    assert response.status_code == 200
    assert client.get("/api/strategies/" + saved["id"] + "/versions").json()[0]["spec"] == original
    job, run = completed(client, saved)
    assert run["version_id"] != original_version
    assert run["dataset"]["source_type"] == "synthetic_demo"
    assert run["quality"]["independent_evaluation"] is False
    assert len(run["equity"]) > 100
    assert run["config"]["execution_delay_bars"] == 1
    versions = client.get("/api/strategies/" + saved["id"] + "/versions").json()
    assert len(versions) == 2 and versions[0]["spec"] == changed
    bad = client.post("/api/community", json={"strategy_id": saved["id"], "version_id": original_version, "run_id": run["id"]})
    assert bad.status_code == 422
    published = client.post("/api/community", json={"strategy_id": saved["id"], "version_id": run["version_id"], "run_id": run["id"]})
    assert published.status_code == 201, published.text
    publication = published.json()
    assert publication["verification"] == "reproducible_snapshot"
    assert publication["reproduction"]["status"] == "matched"
    assert len(publication["reproduction"]["result_sha256"]) == 64
    client.put("/api/strategies/" + saved["id"], json={"name": "Another draft", "spec": original})
    public = TestClient(app)
    visible = public.get("/api/community/" + publication["id"]).json()
    assert visible["spec"] == changed
    assert "email" not in visible and "owner_id" not in visible
    assert public.get("/api/backtests/" + run["id"]).status_code == 401
    demo(public)
    fork = public.post("/api/community/" + publication["id"] + "/fork")
    assert fork.status_code == 201
    assert fork.json()["spec"] == changed and fork.json()["forked_from"] == publication["id"]
    assert client.get("/api/strategies/" + fork.json()["id"]).status_code == 404
    with app.state.db.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE strategy_versions SET spec_hash='tampered' WHERE id=?", (original_version,))
    with app.state.db.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM backtests WHERE id=?", (run["id"],))
    assert client.delete("/api/strategies/" + saved["id"]).status_code == 200
    assert client.get("/api/strategies/" + saved["id"]).status_code == 404
    assert public.get("/api/community/" + publication["id"]).json()["spec"] == changed


def test_invalid_graph_dates_unavailable_capabilities_and_no_secrets(running):
    _, client, _ = running
    demo(client)
    invalid = {"schema_version": 1, "symbol": "BTCUSDT", "timeframe": "4h", "nodes": [], "edges": [], "risk": {"max_exposure": 1}}
    assert client.post("/api/validate", json={"spec": invalid}).json()["valid"] is False
    saved = client.post("/api/strategies", json={"name": "Incomplete draft", "spec": invalid}).json()
    assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h"}).status_code == 422
    assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"end": "2026-01-01"}}).status_code == 422
    assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "../../private.sqlite"}).status_code == 422
    assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"execution_delay_bars": 0}}).status_code == 422
    assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"execution_delay_bars": 7}}).status_code == 422
    assert client.post("/api/ai/generate", json={"prompt": "invent trades"}).status_code == 503
    draft = client.post("/api/ml/drafts", json={"name": "Future research", "config": {"target": "direction", "lookback": 30}}).json()
    assert draft["training_started"] is False
    assert client.get("/api/ml").json()["drafts"][0]["id"] == draft["id"]
    assert client.get("/api/bots").json()["execution_enabled"] is False
    assert client.get("/api/news").json()["is_current"] is False
    assert all(item["is_fixture"] for item in client.get("/api/news").json()["articles"])
    assert client.get("/api/providers").status_code == 200
    assert client.get("/data/platform.sqlite3").status_code == 404
    assert client.get("/.env").status_code == 404


def test_origin_csrf_and_resource_limits(running):
    _, client, _ = running
    assert client.post("/api/auth/demo", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    auth = demo(client)
    assert client.post("/api/validate", headers={"X-CSRF-Token": "wrong"}, json={"spec": {}}).status_code == 403
    assert client.post("/api/validate", headers={"Origin": "https://attacker.invalid"}, json={"spec": {}}).status_code == 403
    large = {"schema_version": 1, "nodes": [{"id": str(i)} for i in range(81)], "edges": []}
    assert client.post("/api/validate", json={"spec": large}).status_code == 413
    assert client.post("/api/validate", content="x" * 200_001, headers={"content-type": "application/json"}).status_code == 413
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/health", headers={"host": "attacker.invalid"}).status_code == 400
    assert client.get("/api/health", headers={"host": "localhost:8710"}).status_code == 200


@pytest.mark.parametrize("declared_length", [None, b"1"])
def test_actual_stream_limit_rejects_misleading_length_before_extra_chunks(running, declared_length):
    app, _, _ = running
    responses, reads = [], []

    async def exercise():
        async def receive():
            reads.append(1)
            assert len(reads) <= 2, "Oversize body must not be consumed further"
            return {"type": "http.request", "body": b"x" * 100_001, "more_body": True}

        async def send(message):
            responses.append(message)

        headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
        headers.append((b"content-length", declared_length) if declared_length is not None else (b"transfer-encoding", b"chunked"))
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/api/validate", "raw_path": b"/api/validate", "root_path": "", "query_string": b"", "server": ("testserver", 80), "client": ("127.0.0.1", 12345), "headers": headers}
        await app(scope, receive, send)

    asyncio.run(exercise())
    assert len(reads) == 2
    assert responses[0]["status"] == 413


def test_publication_runs_exact_saved_inputs_and_rejects_reproduction_mismatch(running, monkeypatch):
    app, client, _ = running
    demo(client)
    saved = strategy(client)
    _, run = completed(client, saved)
    changed = deepcopy(saved["spec"])
    changed["risk"]["max_exposure"] = .25
    assert client.put("/api/strategies/" + saved["id"], json={"name": "New private draft", "spec": changed}).status_code == 200
    original = main.engine.run_backtest
    called = []

    def reproduce_exact(spec, dataset, config):
        assert spec == saved["spec"]
        assert dataset["metadata"]["id"] == run["dataset"]["id"]
        assert config == run["config"]
        called.append(1)
        return original(spec, dataset, config)

    monkeypatch.setattr(main.engine, "run_backtest", reproduce_exact)
    payload = {"strategy_id": saved["id"], "version_id": run["version_id"], "run_id": run["id"]}
    published = client.post("/api/community", json=payload)
    assert published.status_code == 201, published.text
    assert called == [1]

    def reproduce_mismatch(spec, dataset, config):
        result = original(spec, dataset, config)
        result["metrics"]["fees"] += 1
        return result

    monkeypatch.setattr(main.engine, "run_backtest", reproduce_mismatch)
    rejected = client.post("/api/community", json=payload)
    assert rejected.status_code == 409 and "differs" in rejected.json()["detail"]
    assert len(client.get("/api/community").json()) == 1


def test_explicit_extra_allowed_host_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("KEDR_ALLOWED_HOSTS", "research.internal")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/health", headers={"host": "research.internal"}).status_code == 200
        assert client.get("/api/health", headers={"host": "unlisted.internal"}).status_code == 400


def test_restart_keeps_results_and_fails_orphaned_jobs(running):
    app, client, directory = running
    auth = demo(client)
    saved = strategy(client)
    job, run = completed(client, saved)
    with app.state.db.connection() as conn:
        conn.execute("INSERT INTO jobs (id,owner_id,strategy_id,version_id,dataset_id,config_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)", ("interrupted", auth["user"]["id"], saved["id"], run["version_id"], "demo_btc_4h", "{}", "running", "2025-01-01T00:00:00Z"))
    reopened = create_app(directory)
    with TestClient(reopened) as other:
        other.cookies.update(client.cookies)
        other.headers["X-CSRF-Token"] = auth["csrf_token"]
        assert other.get("/api/backtests/" + run["id"]).json()["metrics"] == run["metrics"]
        assert other.get("/api/jobs/interrupted").json()["status"] == "failed"
        assert len(other.get("/api/backtests").json()) == 1


def test_queue_is_bounded_and_worker_errors_are_persisted(running, monkeypatch):
    app, client, _ = running
    demo(client)
    saved = strategy(client)
    _, existing_run = completed(client, saved)
    gate = threading.Event()

    def delayed_failure(*args, **kwargs):
        assert gate.wait(10)
        raise ValueError("Deliberate invalid research input")

    monkeypatch.setattr(main.engine, "run_backtest", delayed_failure)
    ids = []
    try:
        for _ in range(4):
            response = client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h"})
            assert response.status_code == 202, response.text
            ids.append(response.json()["id"])
        assert client.post("/api/backtests", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h"}).status_code == 429
        assert client.post("/api/community", json={"strategy_id": saved["id"], "version_id": existing_run["version_id"], "run_id": existing_run["id"]}).status_code == 429
    finally:
        gate.set()
    for jid in ids:
        for _ in range(500):
            job = client.get("/api/jobs/" + jid).json()
            if job["status"] == "failed":
                break
            time.sleep(.01)
        assert job["status"] == "failed" and job["run_id"] is None
        assert job["error"] == "Deliberate invalid research input"
    assert len(client.get("/api/backtests").json()) == 1
