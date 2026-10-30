"""Bounded fixed research comparisons, separate-process ML and owner preferences."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import math
import random
import re
import statistics
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import data, engine
from .auth import current_user, require_csrf
from .db import encode, identifier, now
from .process_runner import ProcessRunner

log = logging.getLogger("kedr.research")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MLInput(Input):
    name: str = Field(default="Chronological research", min_length=1, max_length=120)
    dataset_id: str = Field(min_length=1, max_length=80)
    target: Literal["direction", "return"] = "direction"
    model_family: Literal["logistic", "ridge"] = "logistic"
    horizon_bars: int = Field(default=6, ge=1, le=42)
    feature_groups: list[Literal["momentum", "volatility", "calendar", "volume"]] = Field(default_factory=lambda: ["momentum", "volatility", "calendar"], min_length=1, max_length=4)
    start: date = date(2022, 1, 1)
    end: date = date(2025, 12, 31)

    @model_validator(mode="after")
    def safe(self):
        if self.start > self.end or self.start < date(2022, 1, 1) or self.end >= date(2026, 1, 1):
            raise ValueError("ML is restricted to the authorized historical 2022–2025 scope.")
        if len(set(self.feature_groups)) != len(self.feature_groups):
            raise ValueError("Feature groups must be distinct.")
        if self.model_family != ("logistic" if self.target == "direction" else "ridge"):
            raise ValueError("Direction uses logistic; signed return uses ridge.")
        return self


class ScenarioInput(Input):
    strategy_id: str = Field(min_length=1, max_length=80)
    version_id: str | None = Field(default=None, max_length=80)
    dataset_id: str = Field(min_length=1, max_length=80)
    scenario_kind: Literal["costs", "partitions", "walk_forward"] = "costs"
    config: dict


class PreferencesInput(Input):
    preferences: dict


class CompareInput(Input):
    run_ids: list[str] = Field(min_length=2, max_length=4)


def _job(row, detail=True):
    value = {k: row[k] for k in ("id", "kind", "name", "status", "error", "created_at", "started_at", "finished_at")}
    value["config"] = json.loads(row["configuration_json"])
    if detail:
        value["result"] = json.loads(row["result_json"]) if row["result_json"] else None
    return value


def _owned(conn, job_id, owner):
    row = conn.execute("SELECT * FROM research_jobs WHERE id=? AND owner_id=?", (job_id, owner)).fetchone()
    if not row:
        raise HTTPException(404, "Research experiment not found")
    return row


def _step(metadata):
    timeframe = metadata["timeframe"]
    periods = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
    if timeframe not in periods:
        raise ValueError("Unsupported research timeframe.")
    return periods[timeframe]


def uncertainty(result, draws=1000):
    """Calendar-week synchronized resampling of saved policy returns.

    These are return-process diagnostics conditional on the fixed observed
    policy, not an artificial-price rerun or independent validation.
    """
    groups = {}
    path = result["equity"]
    for index, point in enumerate(path):
        stamp = datetime.fromisoformat(point["time"].replace("Z", "+00:00"))
        monday = (stamp - timedelta(days=stamp.weekday())).date().isoformat()
        previous = path[index - 1] if index else None
        net = point["equity"] / (previous["equity"] if previous else result["config"]["initial_cash"]) - 1
        passive = point["benchmark_equity"] / (previous["benchmark_equity"] if previous else result["config"]["initial_cash"]) - 1
        groups.setdefault(monday, []).append(net - passive)
    if len(groups) < 20:
        return {"status": "insufficient_calendar_support", "weeks": len(groups), "minimum_weeks": 20, "interval": None}
    clusters = list(groups.values())
    rng, estimates = random.Random(42), []
    for _ in range(draws):
        selected = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        estimates.append(sum(sum(c) for c in selected) / sum(len(c) for c in selected))
    estimates.sort()
    return {"status": "descriptive_only", "weeks": len(groups), "draws": draws, "seed": 42,
            "statistic": "mean one-bar net return minus passive return on matched bars",
            "mean": statistics.mean(value for cluster in clusters for value in cluster),
            "ordinary_95_interval": [estimates[int(draws * .025)], estimates[min(draws - 1, int(draws * .975))]],
            "assumptions": ["Resamples existing synchronized calendar-week clusters, not price paths or a refitted strategy.",
                            "Adjacent weeks and regimes may remain dependent; percentile intervals are approximate.",
                            "Exploratory unadjusted diagnostics; no parameter selection or claim of independent confirmation."]}


def scenarios(spec, dataset, config, kind):
    arms = []
    separation_bars = 8
    separation_days = math.ceil(_step(dataset["metadata"]) * separation_bars / 86_400_000)
    if kind == "costs":
        for label, multiplier in (("half_cost", .5), ("base_cost", 1), ("double_cost", 2)):
            modified = dict(config)
            modified["fee_bps"] = min(100, config.get("fee_bps", 10) * multiplier)
            modified["slippage_bps"] = min(100, config.get("slippage_bps", 2) * multiplier)
            arms.append((label, modified))
    else:
        start, end = date.fromisoformat(config["start"]), date.fromisoformat(config["end"])
        days = (end - start).days + 1
        if days < 90:
            raise ValueError("Chronological period diagnostics require at least 90 requested days.")
        # Exact predeclared thirds with at least eight bars of separation are
        # not reselected from performance. Earlier data still warm indicators;
        # this is a fixed-policy replay, not a fitted-model train/test purge.
        # Configuration accepts dates, so round UP to whole calendar days.
        # Adding a sub-day timedelta directly to date would silently discard it.
        for i, name in enumerate(("development", "validation", "test") if kind == "partitions" else ("forward_1", "forward_2", "forward_3")):
            left = start + timedelta(days=days * i // 3)
            right = start + timedelta(days=days * (i + 1) // 3 - 1)
            if i:
                left += timedelta(days=separation_days)
            if left >= right:
                raise ValueError("Insufficient segment support after fixed execution/context separation.")
            modified = dict(config, start=left.isoformat(), end=right.isoformat())
            arms.append((name, modified))
    results = []
    for name, settings in arms:
        result = engine.run_backtest(spec, dataset, settings)
        results.append({"name": name, "config": result["config"], "metrics": result["metrics"], "benchmarks": result["benchmarks"],
                        "provenance": result["provenance"], "quality": result["quality"], "uncertainty": uncertainty(result)})
    return {"schema_version": 1, "scenario_kind": kind, "arms": results, "selection_performed": False,
            "segment_separation": None if kind == "costs" else {
                "minimum_bars": separation_bars, "calendar_days": separation_days,
                "method": "Round eight native bars up to whole calendar days for the date-only execution API."},
            "model_refitting": False, "independent_validation": False,
            "description": "Fixed cost arms or fixed chronological replay of one immutable strategy. No optimized parameters and no fitting on development or validation outcomes.",
            "limitations": ["Chronological periods are retrospective labels, not untouched evaluation after this interface is inspected.",
                            "Each period restarts cash; retained earlier candles provide causal indicator warm-up only.",
                            "Walk-forward means sequential fixed-policy replay here, not adaptive model refitting.",
                            "Cost inputs are assumptions; candle prices do not establish executable quotes.",
                            "Risk/exposure differ from passive; this comparison does not isolate timing alpha."]}


class ResearchJobs:
    """One running research task, two admitted tasks, separate bounded ML process."""
    def __init__(self, db):
        self.db = db
        self.capacity = threading.BoundedSemaphore(2)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kedr-research")
        self.runner = ProcessRunner()
        self.lifecycle_lock = threading.Lock()

    def close(self):
        self.runner.close()
        self.pool.shutdown(wait=True, cancel_futures=False)

    def submit(self, owner, kind, name, config):
        if not self.capacity.acquire(blocking=False):
            raise HTTPException(429, "The bounded research queue is full (two admitted jobs).")
        jid = identifier()
        try:
            with self.db.connection() as conn:
                if conn.execute("SELECT COUNT(*) FROM research_jobs WHERE owner_id=? AND status IN ('queued','running')", (owner,)).fetchone()[0] >= 1:
                    raise HTTPException(429, "Only one research task per owner may be queued or running.")
                if conn.execute("SELECT COUNT(*) FROM research_jobs WHERE owner_id=?", (owner,)).fetchone()[0] >= 100:
                    raise HTTPException(429, "The local owner research record limit is 100 experiments.")
                conn.execute("INSERT INTO research_jobs (id,owner_id,kind,name,status,configuration_json,created_at) VALUES (?,?,?,?,?,?,?)", (jid, owner, kind, name, "queued", encode(config), now()))
                self.db.audit(conn, owner, "research.queued", jid, {"kind": kind, "configuration_sha256": sha256(encode(config).encode()).hexdigest()})
                value = _job(_owned(conn, jid, owner))
            self.pool.submit(self.execute, jid)
            return value
        except BaseException:
            self.capacity.release()
            raise

    def execute(self, jid):
        try:
            with self.lifecycle_lock, self.db.connection() as conn:
                row = dict(conn.execute("SELECT * FROM research_jobs WHERE id=?", (jid,)).fetchone())
                if row["status"] == "cancelled":
                    return
                conn.execute("UPDATE research_jobs SET status='running',started_at=? WHERE id=?", (now(), jid))
            config = json.loads(row["configuration_json"])
            if row["kind"] == "ml":
                dataset = data.load_dataset(config["dataset_id"])
                if len(dataset["bars"]) > 20000:
                    raise ValueError("This bounded ML worker accepts at most 20,000 candles; select a coarser supported dataset.")
                config["step_ms"] = _step(dataset["metadata"])
                # Values are normalized and allow-listed by the existing adapter.
                payload = {"bars": dataset["bars"], "dataset": dataset["metadata"], "provenance": dataset.get("provenance", {}), "config": config}
                with self.lifecycle_lock, self.db.connection() as conn:
                    if conn.execute("SELECT status FROM research_jobs WHERE id=?", (jid,)).fetchone()[0] == "cancelled":
                        return
                output, resources = self.runner.run(jid, encode(payload).encode())
                result = json.loads(output)
                result["resources"] = resources
            else:
                spec = config["spec"]
                dataset = data.load_dataset_for_strategy(spec, config["dataset_id"])
                result = scenarios(spec, dataset, config["config"], config["scenario_kind"])
                result["dataset"] = dataset["metadata"]
            encoded = encode(result)
            if len(encoded.encode()) > 3_000_000:
                raise ValueError("Research result exceeds its fixed 3 MB saved artifact limit.")
            with self.lifecycle_lock, self.db.connection() as conn:
                if conn.execute("SELECT status FROM research_jobs WHERE id=?", (jid,)).fetchone()[0] == "cancelled":
                    return
                if row["kind"] == "ml":
                    artifact = encode(result["artifact"])
                    model_id = identifier()
                    conn.execute("INSERT INTO model_registry VALUES (?,?,?,?,?,?,?)", (model_id, row["owner_id"], jid, config["model_family"], artifact, sha256(artifact.encode()).hexdigest(), now()))
                    result["model_id"] = model_id
                    encoded = encode(result)
                conn.execute("UPDATE research_jobs SET status='succeeded',result_json=?,finished_at=? WHERE id=?", (encoded, now(), jid))
                self.db.audit(conn, row["owner_id"], "research.completed", jid, {"kind": row["kind"], "result_sha256": sha256(encoded.encode()).hexdigest()})
        except Exception as exc:
            log.exception("Bounded research job failed: %s", jid)
            with self.db.connection() as conn:
                current = conn.execute("SELECT owner_id,status FROM research_jobs WHERE id=?", (jid,)).fetchone()
                if current and current["status"] != "cancelled":
                    message = str(exc)[:400] if isinstance(exc, ValueError) else "Research task failed. Inspect local server logs."
                    conn.execute("UPDATE research_jobs SET status='failed',error=?,finished_at=? WHERE id=?", (message, now(), jid))
                    self.db.audit(conn, current["owner_id"], "research.failed", jid, {"error": message})
        finally:
            self.capacity.release()


class HostedResearchJobs:
    """Shared admission and outbox; the subscriber owns awaited execution."""
    def __init__(self, db, durable):
        self.db, self.durable = db, durable
        self.runner = durable.runner
        self.lifecycle_lock = durable.lifecycle_lock

    def close(self):
        pass

    def submit(self, owner, kind, name, config):
        jid = identifier()
        with self.db.connection() as conn:
            if conn.execute("SELECT COUNT(*) FROM research_jobs WHERE status IN ('queued','running')").fetchone()[0] >= 2:
                raise HTTPException(429, "The shared research queue is full (two admitted jobs).")
            if conn.execute("SELECT COUNT(*) FROM research_jobs WHERE owner_id=? AND status IN ('queued','running')", (owner,)).fetchone()[0] >= 1:
                raise HTTPException(429, "Only one research task per owner may be queued or running.")
            if conn.execute("SELECT COUNT(*) FROM research_jobs WHERE owner_id=?", (owner,)).fetchone()[0] >= 100:
                raise HTTPException(429, "The owner research record limit is 100 experiments.")
            conn.execute("INSERT INTO research_jobs (id,owner_id,kind,name,status,configuration_json,created_at) VALUES (?,?,?,?,?,?,?)", (jid, owner, kind, name, "queued", encode(config), now()))
            self.durable.enqueue(conn, "research", jid, owner)
            self.db.audit(conn, owner, "research.queued", jid, {"kind": kind, "configuration_sha256": sha256(encode(config).encode()).hexdigest()})
            value = _job(_owned(conn, jid, owner))
        self.durable.dispatch_pending_sync(limit=1)
        return value


def register_routes(app, db, helpers):
    router = APIRouter()
    strategy_owned, new_version, validate_spec, config_model = helpers

    @router.get("/api/chart-preferences/{key}")
    def preferences(key: str, user=Depends(current_user)):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", key):
            raise HTTPException(422, "Invalid preference key")
        with db.connection() as conn:
            row = conn.execute("SELECT preferences_json,updated_at FROM chart_preferences WHERE owner_id=? AND preference_key=?", (user["id"], key)).fetchone()
        return {"key": key, "preferences": json.loads(row["preferences_json"]) if row else {}, "updated_at": row["updated_at"] if row else None}

    @router.put("/api/chart-preferences/{key}")
    def save_preferences(key: str, payload: PreferencesInput, user=Depends(require_csrf)):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", key):
            raise HTTPException(422, "Invalid preference key")
        try:
            encoded = encode(payload.preferences)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Preferences must be finite JSON") from exc
        if len(encoded.encode()) > 12000:
            raise HTTPException(413, "Chart preference limit is 12 KB.")
        stamp = now()
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM chart_preferences WHERE owner_id=?", (user["id"],)).fetchone()[0]
            exists = conn.execute("SELECT 1 FROM chart_preferences WHERE owner_id=? AND preference_key=?", (user["id"], key)).fetchone()
            if count >= 30 and not exists:
                raise HTTPException(429, "At most 30 chart preference workspaces per owner.")
            conn.execute("INSERT INTO chart_preferences VALUES (?,?,?,?) ON CONFLICT(owner_id,preference_key) DO UPDATE SET preferences_json=excluded.preferences_json,updated_at=excluded.updated_at", (user["id"], key, encoded, stamp))
        return {"key": key, "preferences": payload.preferences, "updated_at": stamp}

    @router.post("/api/ml/train", status_code=202)
    def train(payload: MLInput, request: Request, user=Depends(require_csrf)):
        choices = {item["id"]: item for item in data.datasets()}
        if payload.dataset_id not in choices or choices[payload.dataset_id].get("status") == "unavailable":
            raise HTTPException(422, "Select an available explicit historical or labelled demo dataset.")
        if choices[payload.dataset_id].get("bars", 0) > 20000:
            raise HTTPException(422, "The bounded ML worker supports at most 20,000 source candles. Select a supported coarser dataset; it will not silently sample or truncate history.")
        return request.app.state.research_jobs.submit(user["id"], "ml", payload.name, payload.model_dump(mode="json"))

    @router.get("/api/ml/experiments")
    def experiments(user=Depends(current_user)):
        with db.connection() as conn:
            return [_job(row, False) for row in conn.execute("SELECT * FROM research_jobs WHERE owner_id=? AND kind='ml' ORDER BY created_at DESC LIMIT 100", (user["id"],))]

    @router.get("/api/ml/experiments/{jid}")
    def experiment(jid: str, request: Request, user=Depends(current_user)):
        with db.connection() as conn:
            row = _owned(conn, jid, user["id"])
            if row["kind"] != "ml":
                raise HTTPException(404, "ML experiment not found")
        service = request.app.state.research_jobs
        if isinstance(service, HostedResearchJobs):
            service.durable.dispatch_pending_sync(limit=1)
        with db.connection() as conn:
            row = _owned(conn, jid, user["id"])
            return _job(row)

    @router.post("/api/ml/experiments/{jid}/cancel")
    def cancel(jid: str, request: Request, user=Depends(require_csrf)):
        service = request.app.state.research_jobs
        with service.lifecycle_lock, db.connection() as conn:
            row = _owned(conn, jid, user["id"])
            if row["kind"] != "ml":
                raise HTTPException(404, "ML experiment not found")
            if row["status"] not in ("queued", "running"):
                raise HTTPException(409, "Only an unfinished ML process can be cancelled.")
            conn.execute("UPDATE research_jobs SET status='cancelled',error='Cancelled by owner; no artifact is registered.',finished_at=? WHERE id=?", (now(), jid))
            killed = service.runner.cancel(jid)
            db.audit(conn, user["id"], "ml.cancelled", jid, {"process_terminated": killed})
            return _job(_owned(conn, jid, user["id"]))

    @router.get("/api/ml/models")
    def models(user=Depends(current_user)):
        with db.connection() as conn:
            return [{"id": row["id"], "experiment_id": row["experiment_id"], "model_family": row["model_family"], "artifact_sha256": row["artifact_sha256"], "artifact": json.loads(row["artifact_json"]), "created_at": row["created_at"]} for row in conn.execute("SELECT * FROM model_registry WHERE owner_id=? ORDER BY created_at DESC LIMIT 100", (user["id"],))]

    @router.post("/api/research/scenarios", status_code=202)
    def scenario(payload: ScenarioInput, request: Request, user=Depends(require_csrf)):
        try:
            checked = config_model.model_validate(payload.config).model_dump(mode="json", exclude_none=True)
        except ValueError as exc:
            raise HTTPException(422, "Invalid bounded backtest configuration") from exc
        choices = {item["id"]: item for item in data.datasets()}
        if payload.dataset_id not in choices or choices[payload.dataset_id].get("status") == "unavailable":
            raise HTTPException(422, "Dataset unavailable")
        with db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = strategy_owned(conn, "strategies", payload.strategy_id, user["id"], active=True)
            if payload.version_id:
                version = conn.execute("SELECT * FROM strategy_versions WHERE id=? AND strategy_id=?", (payload.version_id, payload.strategy_id)).fetchone()
                if not version:
                    raise HTTPException(404, "Version not found")
                vid, spec = version["id"], json.loads(version["spec_json"])
            else:
                spec = json.loads(row["spec_json"])
                vid = new_version(conn, row["id"], spec)
            validate_spec(spec)
        if spec.get("symbol") != choices[payload.dataset_id].get("symbol") or spec.get("timeframe") != choices[payload.dataset_id].get("timeframe"):
            raise HTTPException(422, "Strategy symbol/timeframe must match the dataset.")
        saved = {"strategy_id": payload.strategy_id, "version_id": vid, "spec": spec, "dataset_id": payload.dataset_id,
                 "scenario_kind": payload.scenario_kind, "config": checked}
        if spec.get("schema_version") == 1 and (checked.get("execution_mode") is not None or checked.get("availability_seconds") is not None):
            raise HTTPException(422, "Schema-one scenarios preserve legacy execution; new execution modes require schema two.")
        return request.app.state.research_jobs.submit(user["id"], "scenarios", "Fixed " + payload.scenario_kind, saved)

    @router.get("/api/research/jobs/{jid}")
    def research_job(jid: str, request: Request, user=Depends(current_user)):
        with db.connection() as conn:
            _owned(conn, jid, user["id"])
        service = request.app.state.research_jobs
        if isinstance(service, HostedResearchJobs):
            service.durable.dispatch_pending_sync(limit=1)
        with db.connection() as conn:
            return _job(_owned(conn, jid, user["id"]))

    @router.post("/api/research/compare")
    def compare(payload: CompareInput, user=Depends(require_csrf)):
        if len(set(payload.run_ids)) != len(payload.run_ids):
            raise HTTPException(422, "Select distinct saved runs.")
        runs = []
        with db.connection() as conn:
            for rid in payload.run_ids:
                row = strategy_owned(conn, "backtests", rid, user["id"])
                result = json.loads(row["result_json"])
                runs.append({"id": rid, "strategy_id": row["strategy_id"], "version_id": row["version_id"], "metrics": result["metrics"],
                             "config": json.loads(row["config_json"]), "dataset": json.loads(row["dataset_json"]), "provenance": result["provenance"]})
        matched = len({encode({"data": r["dataset"].get("sha256"), "start": r["provenance"].get("actual_start"), "end": r["provenance"].get("actual_end"), "bars": r["provenance"].get("evaluated_bars")}) for r in runs}) == 1
        return {"runs": runs, "matched_data_calendar": matched, "ranked": False, "independent_validation": False,
                "limitations": ["No winner is selected. Different risks, execution modes, versions or calendars can confound a raw return comparison.",
                                "Repeated historical comparisons are descriptive and do not create an untouched holdout."]}

    app.include_router(router)
