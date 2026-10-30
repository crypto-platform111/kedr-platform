"""Real shared-database API integration; queue transport is isolated in tests."""
import asyncio
from copy import deepcopy

from fastapi.testclient import TestClient

from backend.app.durable_jobs import QueuePublisher
from backend.app.main import create_app
from backend.tests.test_postgres import pg_database  # noqa: F401


def test_hosted_api_persists_job_through_second_instance_and_queue_outage(pg_database, tmp_path, monkeypatch):
    db = pg_database
    monkeypatch.setenv("KEDR_DATABASE_URL", db.database_url)
    monkeypatch.setenv("KEDR_JOB_MODE", "durable")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("VERCEL_URL", "kedr-hosted-example.vercel.app")
    monkeypatch.setenv("CRON_SECRET", "x" * 40)
    monkeypatch.delenv("KEDR_SECURE_COOKIES", raising=False)
    deliveries = []
    fail = [True]

    async def transport(_, payload, key):
        if fail[0]:
            raise RuntimeError("Simulated transport outage")
        deliveries.append((payload, key))
        return "isolated-message"

    monkeypatch.setattr(QueuePublisher, "__call__", transport)
    app = create_app(tmp_path / "never-created")
    with TestClient(app, base_url="https://kedr-hosted-example.vercel.app") as first:
        assert not hasattr(app.state.jobs, "pool")
        assert first.get("/api/health").json()["job_mode"] == "durable"
        login = first.post("/api/auth/demo")
        assert login.status_code == 200
        assert "; Secure" in login.headers["set-cookie"]
        first.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        spec = deepcopy(first.get("/api/templates").json()[0]["spec"])
        strategy = first.post("/api/strategies", json={"name": "Hosted integration", "spec": spec}).json()
        launched = first.post("/api/backtests", json={"strategy_id": strategy["id"], "dataset_id": "demo_btc_4h", "config": {"start": "2023-01-01", "end": "2023-12-31"}})
        assert launched.status_code == 202, launched.text
        jid = launched.json()["id"]
        with db.connection() as conn:
            assert conn.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "queued"
            assert conn.execute("SELECT outbox_pending FROM durable_work WHERE job_id=?", (jid,)).fetchone()[0] == 1
        second_app = create_app(tmp_path / "also-never-created")
        with TestClient(second_app, base_url="https://kedr-hosted-example.vercel.app") as second:
            second.cookies.update(first.cookies)
            assert second.get("/api/auth/me").json()["user"]["id"] == login.json()["user"]["id"]
            assert second.get("/api/internal/dispatch").status_code == 403
            fail[0] = False
            assert second.get("/api/jobs/" + jid).json()["status"] == "queued"
            assert deliveries and deliveries[-1][0] == {"work_key": "backtest:" + jid}
            assert asyncio.run(second_app.state.jobs.handle(deliveries[-1][0]["work_key"])) == "succeeded"
            finished = first.get("/api/jobs/" + jid).json()
            assert finished["status"] == "succeeded"
            run = second.get("/api/backtests/" + finished["run_id"])
            assert run.status_code == 200 and run.json()["dataset"]["source_type"] == "synthetic_demo"
            assert second.get("/api/internal/dispatch", headers={"Authorization": "Bearer " + "x" * 40}).status_code == 200
            third = TestClient(second_app, base_url="https://kedr-hosted-example.vercel.app")
            assert third.post("/api/auth/demo").status_code == 200
            assert third.get("/api/backtests/" + finished["run_id"]).status_code == 404
    assert not (tmp_path / "never-created").exists()
    assert not (tmp_path / "also-never-created").exists()
