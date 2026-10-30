"""Real service persistence/process tests; external AI transport is mocked only in tests."""
from copy import deepcopy
import json
import os
import sqlite3
import time

from fastapi.testclient import TestClient
import pytest

from backend.app import copilot, data, ml_worker, research
from backend.app.db import encode
from backend.app.main import create_app
from backend.app.process_runner import ProcessRunner


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("KEDR_AI_PROVIDER", "disabled")
    app = create_app(tmp_path)
    with TestClient(app) as client:
        auth = client.post("/api/auth/demo", json={}).json()
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        yield app, client


def strategy(client):
    spec = client.get("/api/templates").json()[0]["spec"]
    response = client.post("/api/strategies", json={"name": "Studio", "spec": spec})
    assert response.status_code == 201, response.text
    return response.json()


def conversation(client, saved):
    response = client.post(f"/api/strategies/{saved['id']}/conversations", json={"locale": "en"})
    assert response.status_code == 201
    return response.json()["id"]


def connected(monkeypatch):
    # Literal test credentials, never a user key or legacy environment.
    monkeypatch.setenv("KEDR_AI_PROVIDER", "openai")
    monkeypatch.setenv("KEDR_AI_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setenv("KEDR_AI_MODEL", "configured-test-model")
    monkeypatch.setenv("KEDR_AI_INPUT_USD_PER_MILLION", "1")
    monkeypatch.setenv("KEDR_AI_OUTPUT_USD_PER_MILLION", "1")
    monkeypatch.setenv("KEDR_AI_DAILY_TOKEN_LIMIT", "1000000")


def poll(client, route):
    for _ in range(400):
        value = client.get(route).json()
        if value["status"] in ("succeeded", "failed", "cancelled"):
            return value
        time.sleep(.025)
    pytest.fail("Bounded test task did not finish")


def test_copilot_offline_is_explicit_persistent_and_private(studio):
    app, client = studio
    saved = strategy(client)
    cid = conversation(client, saved)
    assert client.get("/api/copilot/status").json()["status"] == "not_connected"
    reply = client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Create an EMA crossover"}).json()
    assert reply["message"]["mode"] == "offline_rules"
    assert reply["proposal"] is None
    history = client.get(f"/api/copilot/conversations/{cid}").json()
    assert [item["role"] for item in history["messages"]] == ["user", "assistant"]
    assert client.get(f"/api/strategies/{saved['id']}").json()["spec_hash"] == saved["spec_hash"]
    other = TestClient(app)
    auth = other.post("/api/auth/demo", json={}).json()
    other.headers["X-CSRF-Token"] = auth["csrf_token"]
    assert other.get(f"/api/copilot/conversations/{cid}").status_code == 404
    assert other.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Steal"}).status_code == 404


def test_configured_provider_requires_per_request_consent(studio, monkeypatch):
    _, client = studio
    saved = strategy(client)
    cid = conversation(client, saved)
    connected(monkeypatch)
    def forbidden(*args):
        pytest.fail("External adapter must not run without explicit request consent")
    monkeypatch.setattr(copilot, "call_openai", forbidden)
    response = client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Explain", "consent_external": False})
    assert response.status_code == 200
    assert response.json()["message"]["mode"] == "offline_rules"
    assert client.get("/api/copilot/status").json()["owner_usage"]["requests"] == 0


def test_valid_ai_proposal_requires_explicit_approval_then_immutable_rollback(studio, monkeypatch):
    app, client = studio
    saved = strategy(client)
    cid = conversation(client, saved)
    connected(monkeypatch)
    changed = deepcopy(saved["spec"])
    next(node for node in changed["nodes"] if node["type"] == "sma")["params"]["period"] = 25
    def transport(context, config, usage_id):
        assert context["strategy"] == saved["spec"]
        return {"reply": "Review the changed moving average before applying it.", "proposed_spec_json": encode(changed), "numeric_claims": [], "limitations": ["Retrospective research only."]}, {"input_tokens": 10, "output_tokens": 20}, {"attempts": 1}
    monkeypatch.setattr(copilot, "call_openai", transport)
    response = client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Change the period", "consent_external": True})
    assert response.status_code == 200, response.text
    proposal = response.json()["proposal"]
    assert proposal["status"] == "pending" and len(proposal["diff"]["changed_nodes"]) == 1
    assert client.get(f"/api/strategies/{saved['id']}").json()["spec"] == saved["spec"]
    approve = client.post(f"/api/copilot/proposals/{proposal['id']}/approve", json={"expected_spec_hash": saved["spec_hash"]})
    assert approve.status_code == 200, approve.text
    assert client.get(f"/api/strategies/{saved['id']}").json()["spec"] == changed
    rollback = client.post(f"/api/copilot/proposals/{proposal['id']}/rollback", json={"expected_spec_hash": approve.json()["spec_hash"]})
    assert rollback.status_code == 200
    assert rollback.json()["spec"] == saved["spec"]
    versions = client.get(f"/api/strategies/{saved['id']}/versions").json()
    assert len(versions) == 3 and versions[-1]["spec"] == saved["spec"]
    with app.state.db.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE copilot_proposals SET proposed_spec_json='{}'")
    assert client.post(f"/api/copilot/proposals/{proposal['id']}/approve", json={"expected_spec_hash": saved["spec_hash"]}).status_code == 409


def test_ai_invalid_graph_numeric_claim_and_quota_fail_closed(studio, monkeypatch):
    app, client = studio
    saved = strategy(client)
    cid = conversation(client, saved)
    connected(monkeypatch)
    def invalid(*args):
        return {"reply": "Measured result is guaranteed.", "proposed_spec_json": None, "numeric_claims": [{"path": "metrics.invented", "value": 99}], "limitations": []}, {"input_tokens": 1, "output_tokens": 1}, {}
    monkeypatch.setattr(copilot, "call_openai", invalid)
    response = client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Invent profit", "consent_external": True})
    assert response.status_code == 502
    assert client.get(f"/api/copilot/conversations/{cid}").json()["messages"] == []
    with app.state.db.connection() as conn:
        usage = conn.execute("SELECT * FROM ai_usage").fetchone()
        assert usage["status"] == "failed" and usage["accounted_tokens"] == usage["reserved_tokens"] > 0
    monkeypatch.setenv("KEDR_AI_DAILY_REQUEST_LIMIT", "1")
    assert client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Retry", "consent_external": True}).status_code == 429
    broken = deepcopy(saved["spec"])
    broken["nodes"][0]["type"] = "arbitrary_python"
    with pytest.raises(ValueError, match="validation"):
        copilot.validate_response({"reply": "Review.", "proposed_spec_json": encode(broken), "numeric_claims": [], "limitations": []}, {})
    with pytest.raises(ValueError, match="Numeric AI prose"):
        copilot.validate_response({"reply": "Profit is 99 percent", "proposed_spec_json": None, "numeric_claims": [], "limitations": []}, {})


def test_approval_detects_intervening_draft_edit(studio, monkeypatch):
    _, client = studio
    saved = strategy(client)
    cid = conversation(client, saved)
    connected(monkeypatch)
    monkeypatch.setattr(copilot, "call_openai", lambda *args: ({"reply": "Review.", "proposed_spec_json": encode(saved["spec"]), "numeric_claims": [], "limitations": []}, {"input_tokens": 1, "output_tokens": 1}, {}))
    proposal = client.post(f"/api/copilot/conversations/{cid}/messages", json={"message": "Preview", "consent_external": True}).json()["proposal"]
    changed = deepcopy(saved["spec"])
    changed["nodes"][0]["position"] = {"x": 1, "y": 2}
    assert client.put(f"/api/strategies/{saved['id']}", json={"name": saved["name"], "spec": changed}).status_code == 200
    assert client.post(f"/api/copilot/proposals/{proposal['id']}/approve", json={"expected_spec_hash": saved["spec_hash"]}).status_code == 409


def test_chart_preferences_are_bounded_and_owner_scoped(studio):
    app, client = studio
    settings = {"indicators": ["ema", "rsi"], "symbol": "BTCUSDT", "period": 20}
    assert client.put("/api/chart-preferences/market", json={"preferences": settings}).status_code == 200
    assert client.get("/api/chart-preferences/market").json()["preferences"] == settings
    assert client.put("/api/chart-preferences/market", json={"preferences": {"overflow": "x" * 12001}}).status_code == 413
    second = TestClient(app)
    second.post("/api/auth/demo", json={})
    assert second.get("/api/chart-preferences/market").json()["preferences"] == {}


def ml_config():
    return {"dataset_id": "demo_btc_4h", "name": "Real bounded test", "target": "direction", "model_family": "logistic", "horizon_bars": 6,
            "feature_groups": ["momentum", "volatility", "calendar"], "start": "2023-01-01", "end": "2023-12-31", "step_ms": 14400000}


def test_ml_features_do_not_change_when_future_values_change_and_splits_purge():
    dataset = data.load_dataset("demo_btc_4h")
    bars = dataset["bars"]
    before = ml_worker.features_at(bars, 200, ["momentum", "volatility", "calendar"], 14400000)
    mutated = deepcopy(bars)
    for bar in mutated[201:]:
        bar["close"] *= 100
    assert before == ml_worker.features_at(mutated, 200, ["momentum", "volatility", "calendar"], 14400000)
    _, train, validation, test, manifest = ml_worker.observations(bars, ml_config())
    assert train[-1]["label_end_index"] < validation[0]["bar_index"] - 1
    assert validation[-1]["label_end_index"] < test[0]["bar_index"] - 1
    assert train[0]["origin"] > train[0]["signal_candle_open"]
    assert all(b["reference"] >= a["label_end"] for a, b in zip(test, test[1:]))
    assert manifest["purged_origins"] > 0


def test_real_ml_process_registry_reload_permissions_and_no_strategy_attachment(studio):
    app, client = studio
    config = ml_config()
    config.pop("step_ms")
    response = client.post("/api/ml/train", json=config)
    assert response.status_code == 202, response.text
    jid = response.json()["id"]
    finished = poll(client, f"/api/ml/experiments/{jid}")
    assert finished["status"] == "succeeded", finished
    result = finished["result"]
    assert result["resources"]["separate_process"] is True and result["resources"]["worker_pid"] != os.getpid()
    assert result["resources"]["memory_limit_mib"] == 256 and result["reload_max_error"] == 0
    assert result["metrics"]["test"]["n"] >= 20 and result["baseline_metrics"]["test"]["n"] == result["metrics"]["test"]["n"]
    assert result["artifact"]["strategy_node_executable"] is False
    models = client.get("/api/ml/models").json()
    assert len(models) == 1 and models[0]["id"] == result["model_id"]
    with app.state.db.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE model_registry SET artifact_json='{}'")
    other = TestClient(app)
    other.post("/api/auth/demo", json={})
    assert other.get(f"/api/ml/experiments/{jid}").status_code == 404
    assert other.get("/api/ml/models").json() == []
    assert client.post("/api/ml/train", json={**config, "end": "2026-01-01"}).status_code == 422
    assert client.post("/api/ml/train", json={**config, "model_family": "ridge"}).status_code == 422


def test_ridge_real_fit_and_insufficient_capacity_not_relaxed():
    dataset = data.load_dataset("demo_btc_4h")
    config = {**ml_config(), "target": "return", "model_family": "ridge"}
    result = ml_worker.run_experiment({"bars": dataset["bars"], "dataset": dataset["metadata"], "config": config})
    assert result["summary"]["score_name"] == "mae_bps"
    assert result["reload_max_error"] == 0
    with pytest.raises(ValueError, match="120"):
        ml_worker.run_experiment({"bars": dataset["bars"][:120], "dataset": dataset["metadata"], "config": config})


def test_fixed_cost_scenarios_and_comparison_reject_private_ids(studio):
    app, client = studio
    saved = strategy(client)
    response = client.post("/api/research/scenarios", json={"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "scenario_kind": "costs", "config": {"start": "2023-01-01", "end": "2023-12-31"}})
    assert response.status_code == 202, response.text
    finished = poll(client, "/api/research/jobs/" + response.json()["id"])
    assert finished["status"] == "succeeded", finished
    result = finished["result"]
    assert [arm["name"] for arm in result["arms"]] == ["half_cost", "base_cost", "double_cost"]
    assert result["selection_performed"] is False and result["independent_validation"] is False
    assert result["arms"][0]["uncertainty"]["seed"] == 42
    assert client.get(f"/api/strategies/{saved['id']}").json()["spec"] == saved["spec"]
    assert client.post("/api/research/compare", json={"run_ids": ["unknown", "other"]}).status_code == 404
    assert client.post("/api/research/compare", json={"run_ids": ["same", "same"]}).status_code == 422


def test_real_openai_adapter_http_contract_is_strict_bounded_and_not_an_arbitrary_url(monkeypatch):
    reply = {"reply": "Review the measured evidence.", "proposed_spec_json": None, "numeric_claims": [], "limitations": ["Historical results are descriptive."]}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self, limit):
            assert limit == 400001
            return encode({"status": "completed", "id": "unit-response", "model": "unit-model", "output": [{"type": "message", "content": [{"type": "output_text", "text": encode(reply)}]}], "usage": {"input_tokens": 10, "output_tokens": 20}}).encode()
    def request(req, timeout):
        assert req.full_url == "https://api.openai.com/v1/responses" and timeout == 20
        body = json.loads(req.data)
        assert body["store"] is False and body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["type"] == "json_schema" and "tools" not in body
        assert req.get_header("Authorization") == "Bearer unit-key"
        return Response()
    monkeypatch.setattr(copilot, "urlopen", request)
    result, usage, metadata = copilot.call_openai({"message": "Explain", "evidence": {}}, {"model": "unit-model", "key": "unit-key", "timeout": 20, "max_output": 1500}, "unit-reservation")
    assert result == reply and usage["output_tokens"] == 20 and metadata["attempts"] == 1


def test_ml_prestart_cancellation_really_terminates_process():
    runner = ProcessRunner()
    assert runner.cancel("cancel-before-registration") is False
    dataset = data.load_dataset("demo_btc_4h")
    payload = encode({"bars": dataset["bars"], "dataset": dataset["metadata"], "config": ml_config()}).encode()
    with pytest.raises((ValueError, BrokenPipeError, OSError)):
        runner.run("cancel-before-registration", payload)
    assert runner.processes == {}
    runner.close()


def test_legacy_run_cannot_be_reinterpreted_with_new_execution_config(studio):
    _, client = studio
    saved = strategy(client)
    for endpoint, body in (("/api/backtests", {"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "config": {"execution_mode": "next_bar_open_optimistic", "availability_seconds": 0}}),
                           ("/api/research/scenarios", {"strategy_id": saved["id"], "dataset_id": "demo_btc_4h", "scenario_kind": "costs", "config": {"execution_mode": "full_bar_embargo"}})):
        assert client.post(endpoint, json=body).status_code == 422


@pytest.mark.parametrize("timeframe,step,expected_days", [("1m", 60000, 1), ("4h", 14400000, 2), ("1d", 86400000, 8)])
def test_chronological_scenario_separation_never_discards_subday_bars(monkeypatch, timeframe, step, expected_days):
    from datetime import date
    configs = []
    def replay(spec, dataset, config):
        configs.append(config)
        return {"config": config, "metrics": {}, "benchmarks": {}, "provenance": {}, "quality": {}}
    monkeypatch.setattr(research.engine, "run_backtest", replay)
    monkeypatch.setattr(research, "uncertainty", lambda result: {})
    result = research.scenarios({}, {"metadata": {"timeframe": timeframe}},
                                {"start": "2023-01-01", "end": "2023-12-31"}, "partitions")
    assert result["segment_separation"]["calendar_days"] == expected_days
    for previous, current in zip(configs, configs[1:]):
        # End dates are inclusive; the skipped full days start after that date.
        skipped_days = (date.fromisoformat(current["start"]) - date.fromisoformat(previous["end"])).days - 1
        assert skipped_days == expected_days
        assert skipped_days * 86_400_000 >= step * 8
