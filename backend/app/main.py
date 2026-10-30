"""KEDR local application API: isolated identities, immutable research and honest jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import asynccontextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
import json
import hmac
import logging
import os
import re
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import data, domain, engine, copilot, research
from .market import router as market_router
from .auth import COOKIE_NAME, current_identity, current_user, new_session, password_hash, password_matches, public_user, require_csrf
from .db import Database, encode, identifier, now
from .contracts import GenerationRequest
from .providers import news_fixture, provider_statuses
from .hosting import allowed_hosts, allowed_origins, configured_database_url, vercel_cloud
from .hosted_response import HostedJSONResponse
from starlette.responses import JSONResponse

log = logging.getLogger("kedr.api")
BASE = Path(__file__).resolve().parents[2]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Registration(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    name: str = Field(min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Name must not be empty")
        return value.strip()


class Login(Input):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Profile(Input):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    level: str | None = None
    locale: str | None = None
    timezone: str | None = None
    theme: str | None = None

    @model_validator(mode="after")
    def valid_options(self):
        allowed = {"level": {"beginner", "intermediate", "advanced"}, "locale": {"ru", "en"}, "theme": {"dark", "light", "system"}}
        for key, options in allowed.items():
            if getattr(self, key) is not None and getattr(self, key) not in options:
                raise ValueError(f"Unsupported {key}")
        if self.name is not None and not self.name.strip():
            raise ValueError("Name must not be empty")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Unknown timezone")
        return self


class StrategyInput(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    spec: dict

    @field_validator("name")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Name must not be empty")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def reasonable_tags(cls, values):
        if any(not isinstance(value, str) or len(value) > 40 for value in values):
            raise ValueError("Tags must be strings of at most 40 characters")
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ValidationInput(Input):
    spec: dict


class BacktestConfig(Input):
    start: date = date(2022, 1, 1)
    end: date = date(2025, 12, 31)
    initial_cash: float = Field(default=10000, ge=10, le=1e9, allow_inf_nan=False)
    fee_bps: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)
    slippage_bps: float = Field(default=2, ge=0, le=100, allow_inf_nan=False)
    execution_delay_bars: int = Field(default=1, ge=1, le=6)
    execution_mode: str | None = None
    availability_seconds: int | None = Field(default=None, ge=0, le=60)

    @model_validator(mode="after")
    def historical_bounds(self):
        if self.start > self.end:
            raise ValueError("Start must be before end")
        if self.start < date(2017, 1, 1) or self.end >= date(2026, 1, 1):
            raise ValueError("This application is restricted to historical dates before 2026")
        if self.execution_mode not in (None, "full_bar_embargo", "next_bar_open_optimistic"):
            raise ValueError("Unsupported execution mode")
        if self.execution_mode == "next_bar_open_optimistic" and (self.execution_delay_bars != 1 or self.availability_seconds != 0):
            raise ValueError("Optimistic next-open mode requires delay one and explicit zero assumed availability seconds")
        return self


class BacktestInput(Input):
    strategy_id: str
    version_id: str | None = None
    dataset_id: str
    config: BacktestConfig = Field(default_factory=BacktestConfig)


class PublicationInput(Input):
    strategy_id: str
    version_id: str
    run_id: str
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=12)

    @field_validator("tags")
    @classmethod
    def reasonable_tags(cls, value):
        return None if value is None else StrategyInput.reasonable_tags(value)


class MLDraftInput(Input):
    name: str = Field(default="Research draft", min_length=1, max_length=120)
    config: dict


def _validate_spec(spec):
    try:
        size = len(encode(spec))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Strategy values must be finite JSON data") from exc
    nodes, edges = spec.get("nodes"), spec.get("edges")
    if size > 150_000 or (isinstance(nodes, list) and len(nodes) > 80) or (isinstance(edges, list) and len(edges) > 150):
        raise HTTPException(413, "Strategy graph exceeds the local limit")
    try:
        return domain.validate_strategy(spec)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, "Malformed strategy graph") from exc


def _require_valid(spec):
    result = _validate_spec(spec)
    if not result.get("valid"):
        raise HTTPException(422, result)


def _strategy(row) -> dict:
    value = dict(row)
    value["tags"] = json.loads(value.pop("tags_json"))
    value["spec"] = json.loads(value.pop("spec_json"))
    value["spec_hash"] = sha256(encode(value["spec"]).encode("utf-8")).hexdigest()
    value.pop("deleted_at", None)
    return value


def _version(row) -> dict:
    value = dict(row)
    value["spec"] = json.loads(value.pop("spec_json"))
    return value


def _owned(conn, table, object_id, owner_id, *, active=False):
    # Call sites supply only fixed table names, never user input.
    if table not in {"strategies", "jobs", "backtests"}:
        raise ValueError("Unsupported ownership table")
    row = conn.execute(f"SELECT * FROM {table} WHERE id=? AND owner_id=?" + (" AND deleted_at IS NULL" if active else ""), (object_id, owner_id)).fetchone()
    if not row:
        raise HTTPException(404, "Resource not found")
    return row


def _new_version(conn, strategy_id, spec):
    number = conn.execute("SELECT COALESCE(MAX(number),0)+1 FROM strategy_versions WHERE strategy_id=?", (strategy_id,)).fetchone()[0]
    vid, stamp, payload = identifier(), now(), encode(spec)
    conn.execute("INSERT INTO strategy_versions VALUES (?,?,?,?,?,?)", (vid, strategy_id, number, payload, sha256(payload.encode("utf-8")).hexdigest(), stamp))
    conn.execute("UPDATE strategies SET latest_version_id=?,version_number=?,updated_at=? WHERE id=?", (vid, number, stamp, strategy_id))
    return vid


def _new_strategy(conn, owner_id, name, description, tags, spec, forked_from=None):
    sid, stamp = identifier(), now()
    conn.execute("INSERT INTO strategies (id,owner_id,name,description,tags_json,spec_json,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (sid, owner_id, name, description, encode(tags), encode(spec), forked_from, stamp, stamp))
    _new_version(conn, sid, spec)
    return sid


def _job(row):
    value = {key: row[key] for key in ("id", "status", "run_id", "strategy_id", "version_id", "dataset_id", "error", "created_at", "started_at", "finished_at")}
    return value


def _run(row):
    value = json.loads(row["result_json"])
    value.update({key: row[key] for key in ("id", "strategy_id", "version_id", "status", "created_at")})
    value["dataset"] = json.loads(row["dataset_json"])
    value["config"] = json.loads(row["config_json"])
    return value


def _publication(row, detail=False):
    value = {key: row[key] for key in ("id", "name", "author", "description", "version_id", "run_id", "created_at")}
    reproduction = json.loads(row["reproduction_json"]) if row["reproduction_json"] else None
    value.update(tags=json.loads(row["tags_json"]), dataset=json.loads(row["dataset_json"]), metrics=json.loads(row["metrics_json"]), verification="reproducible_snapshot" if reproduction else "saved_snapshot", reproduction=reproduction)
    spec = json.loads(row["spec_json"])
    value["symbol"] = spec.get("symbol")
    if detail:
        value["spec"] = spec
    return value


class LocalJobs:
    """One CPU job at a time, four admitted jobs total; saved immutable inputs."""
    def __init__(self, db):
        self.db = db
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kedr-backtest")
        self.capacity = threading.BoundedSemaphore(4)

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)

    def reproduce(self, spec, dataset_id, config):
        if not self.capacity.acquire(blocking=False):
            raise HTTPException(429, "The local queue is full; wait before reproducing a publication.")

        def replay():
            try:
                return engine.run_backtest(spec, data.load_dataset_for_strategy(spec, dataset_id), config)
            finally:
                self.capacity.release()

        try:
            future = self.pool.submit(replay)
        except BaseException:
            self.capacity.release()
            raise
        try:
            return future.result(timeout=60)
        except FutureTimeout as exc:
            # Work remains bounded in the sole worker; its finally releases admission.
            raise HTTPException(503, "Publication replay did not complete within 60 seconds; no publication was created.") from exc
        except ValueError as exc:
            raise HTTPException(422, "Publication replay failed: " + str(exc)[:300]) from exc

    def execute(self, job_id):
        try:
            with self.db.connection() as conn:
                job = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
                if job["status"] == "cancelled":
                    return
                version = conn.execute("SELECT * FROM strategy_versions WHERE id=?", (job["version_id"],)).fetchone()
                spec = json.loads(version["spec_json"])
                changed = conn.execute("UPDATE jobs SET status='running',started_at=? WHERE id=? AND status='queued'", (now(), job_id)).rowcount
                if not changed:
                    return
            dataset = data.load_dataset_for_strategy(spec, job["dataset_id"])
            result = engine.run_backtest(spec, dataset, json.loads(job["config_json"]))
            run_id = identifier()
            with self.db.connection() as conn:
                conn.execute("INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?)", (run_id, job["owner_id"], job["strategy_id"], job["version_id"], encode(dataset["metadata"]), job["config_json"], encode(result), "succeeded", now()))
                conn.execute("UPDATE jobs SET status='succeeded',run_id=?,finished_at=? WHERE id=?", (run_id, now(), job_id))
                self.db.audit(conn, job["owner_id"], "backtest.completed", run_id, {"version_id": job["version_id"], "dataset_id": job["dataset_id"]})
        except Exception as exc:
            log.exception("Backtest job failed: %s", job_id)
            # Engine input/data errors are actionable; unexpected errors do not leak paths or internals.
            message = str(exc)[:500] if isinstance(exc, ValueError) else "Local job failed. Inspect the local server log."
            with self.db.connection() as conn:
                conn.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=?", (message, now(), job_id))
                row = conn.execute("SELECT owner_id FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row:
                    self.db.audit(conn, row["owner_id"], "backtest.failed", job_id, {"error": message})
        finally:
            self.capacity.release()


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    cloud = vercel_cloud()
    database_url = configured_database_url()
    if cloud and not database_url:
        raise RuntimeError("Vercel hosting requires KEDR_DATABASE_URL for shared PostgreSQL storage; ephemeral SQLite is disabled.")
    db = Database(data_dir or os.environ.get("KEDR_DATA_DIR", BASE / "data"), database_url=database_url)
    job_mode = os.environ.get("KEDR_JOB_MODE", "durable" if db.backend == "postgresql" else "local")
    if job_mode not in ("local", "durable") or (job_mode == "durable" and db.backend != "postgresql") or (cloud and job_mode != "durable"):
        raise RuntimeError("Hosted jobs require durable mode with shared PostgreSQL; local mode is only for local development.")
    db.initialize()

    @asynccontextmanager
    async def lifespan(app):
        if job_mode == "durable":
            from .durable_jobs import DurableJobs
            app.state.jobs = DurableJobs(db)
            app.state.research_jobs = research.HostedResearchJobs(db, app.state.jobs)
        else:
            with db.connection() as conn:
                conn.execute("UPDATE jobs SET status='failed',error='Server restarted before completion; submit a new run.',finished_at=? WHERE status IN ('queued','running')", (now(),))
                conn.execute("UPDATE research_jobs SET status='failed',error='Server restarted; no unfinished model artifact was registered.',finished_at=? WHERE status IN ('queued','running')", (now(),))
            app.state.jobs = LocalJobs(db)
            app.state.research_jobs = research.ResearchJobs(db)
        yield
        app.state.research_jobs.close()
        app.state.jobs.close()

    app = FastAPI(title="KEDR Research API", version="0.2.0", lifespan=lifespan,
                  default_response_class=HostedJSONResponse if cloud else JSONResponse)
    app.state.db = db
    app.state.job_mode = job_mode
    app.state.auth_attempts = {}
    app.state.auth_lock = threading.Lock()
    trusted_origins = allowed_origins()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
    app.add_middleware(CORSMiddleware, allow_origins=trusted_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def guard_requests(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {f"{request.url.scheme}://{request.url.netloc}", *trusted_origins}
            if origin and origin not in allowed:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Cross-origin mutation rejected"}, status_code=403)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 200_000):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Request exceeds the local body limit"}, status_code=413)
            # Bound actual bytes independently of Content-Length, including
            # chunked and deliberately misleading clients. Cache the bounded
            # body for Starlette/FastAPI's downstream JSON parser.
            chunks, received = [], 0
            async for chunk in request.stream():
                received += len(chunk)
                if received > 200_000:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({"detail": "Request exceeds the local body limit"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def auth_rate_limit(request):
        key = request.client.host if request.client else "local"
        if db.backend == "postgresql":
            if not db.record_auth_attempt(key):
                raise HTTPException(429, "Too many authentication attempts; wait five minutes")
            return
        clock = time.monotonic()
        with app.state.auth_lock:
            attempts = [stamp for stamp in app.state.auth_attempts.get(key, []) if stamp > clock - 300]
            if len(attempts) >= 30:
                raise HTTPException(429, "Too many authentication attempts; wait five minutes")
            app.state.auth_attempts[key] = attempts + [clock]
            if len(app.state.auth_attempts) > 1000:
                app.state.auth_attempts = {key: value for key, value in app.state.auth_attempts.items() if value[-1] > clock - 300}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "application": "KEDR", "mode": "hosted_research" if job_mode == "durable" else "local_research", "version": "0.2.0", "execution_enabled": False, "storage": db.backend, "job_mode": job_mode}

    @app.get("/api/internal/dispatch", include_in_schema=False)
    async def dispatch(request: Request):
        secret = os.environ.get("CRON_SECRET", "")
        if len(secret) < 32:
            raise HTTPException(503, "The scheduled dispatcher requires a configured server-only secret.")
        if not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + secret):
            raise HTTPException(403, "Scheduled dispatcher authorization required")
        if request.app.state.job_mode != "durable":
            raise HTTPException(409, "Durable dispatch requires shared PostgreSQL storage")
        return await request.app.state.jobs.dispatch_pending(limit=20)

    @app.get("/api/auth/me")
    def me(request: Request):
        identity = current_identity(request)
        return {"user": public_user(identity), "csrf_token": identity["csrf_token"]}

    @app.post("/api/auth/demo")
    def demo(request: Request, response: Response):
        auth_rate_limit(request)
        uid, stamp = identifier(), now()
        with db.connection() as conn:
            conn.execute("INSERT INTO users (id,email,name,is_demo,created_at) VALUES (?,?,?,?,?)", (uid, f"demo-{uid}@local.invalid", "Исследователь", 1, stamp))
            db.audit(conn, uid, "auth.demo_created", uid)
            user = public_user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        return {"user": user, "csrf_token": new_session(db, uid, response)}

    @app.post("/api/auth/register", status_code=201)
    def register(payload: Registration, request: Request, response: Response):
        auth_rate_limit(request)
        uid = identifier()
        try:
            with db.connection() as conn:
                conn.execute("INSERT INTO users (id,email,password_hash,name,created_at) VALUES (?,?,?,?,?)", (uid, payload.email, password_hash(payload.password), payload.name, now()))
                db.audit(conn, uid, "auth.registered", uid)
                user = public_user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "An account with this email already exists") from exc
        return {"user": user, "csrf_token": new_session(db, uid, response)}

    @app.post("/api/auth/login")
    def login(payload: Login, request: Request, response: Response):
        auth_rate_limit(request)
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE AND is_demo=0", (payload.email.strip(),)).fetchone()
            valid = password_matches(payload.password, row["password_hash"] if row else None)
            if not valid:
                raise HTTPException(401, "Invalid email or password")
            db.audit(conn, row["id"], "auth.logged_in", row["id"])
            user = public_user(row)
        return {"user": user, "csrf_token": new_session(db, user["id"], response)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user=Depends(require_csrf)):
        identity = current_identity(request)
        with db.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (identity["token_hash"],))
            db.audit(conn, user["id"], "auth.logged_out")
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
        return {"ok": True}

    @app.patch("/api/profile")
    def update_profile(payload: Profile, user=Depends(require_csrf)):
        changes = payload.model_dump(exclude_none=True)
        if "name" in changes:
            changes["name"] = changes["name"].strip()
        with db.connection() as conn:
            if changes:
                conn.execute("UPDATE users SET " + ",".join(f"{key}=?" for key in changes) + " WHERE id=?", (*changes.values(), user["id"]))
                db.audit(conn, user["id"], "profile.updated", user["id"], {"fields": list(changes)})
            return public_user(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())

    @app.get("/api/templates")
    def templates():
        return domain.templates()

    @app.get("/api/nodes")
    def nodes():
        return domain.node_catalog()

    @app.get("/api/datasets")
    def datasets():
        return data.datasets()

    @app.get("/api/providers")
    def providers():
        return provider_statuses()

    @app.post("/api/validate")
    def validate(payload: ValidationInput, user=Depends(require_csrf)):
        return _validate_spec(payload.spec)

    @app.get("/api/strategies")
    def strategies(user=Depends(current_user)):
        with db.connection() as conn:
            return [_strategy(row) for row in conn.execute("SELECT * FROM strategies WHERE owner_id=? AND deleted_at IS NULL ORDER BY updated_at DESC,id", (user["id"],))]

    @app.post("/api/strategies", status_code=201)
    def save_strategy(payload: StrategyInput, user=Depends(require_csrf)):
        # Incomplete visual drafts may be saved; validation still gates every run.
        _validate_spec(payload.spec)
        with db.connection() as conn:
            sid = _new_strategy(conn, user["id"], payload.name, payload.description, payload.tags, payload.spec)
            db.audit(conn, user["id"], "strategy.created", sid)
            return _strategy(_owned(conn, "strategies", sid, user["id"], active=True))

    @app.get("/api/strategies/{sid}")
    def get_strategy(sid: str, user=Depends(current_user)):
        with db.connection() as conn:
            return _strategy(_owned(conn, "strategies", sid, user["id"], active=True))

    @app.put("/api/strategies/{sid}")
    def edit_strategy(sid: str, payload: StrategyInput, user=Depends(require_csrf)):
        _validate_spec(payload.spec)
        with db.connection() as conn:
            _owned(conn, "strategies", sid, user["id"], active=True)
            conn.execute("UPDATE strategies SET name=?,description=?,tags_json=?,spec_json=?,updated_at=? WHERE id=?", (payload.name, payload.description, encode(payload.tags), encode(payload.spec), now(), sid))
            db.audit(conn, user["id"], "strategy.draft_saved", sid)
            return _strategy(_owned(conn, "strategies", sid, user["id"], active=True))

    @app.delete("/api/strategies/{sid}")
    def delete_strategy(sid: str, user=Depends(require_csrf)):
        with db.connection() as conn:
            _owned(conn, "strategies", sid, user["id"], active=True)
            conn.execute("UPDATE strategies SET deleted_at=? WHERE id=?", (now(), sid))
            db.audit(conn, user["id"], "strategy.archived", sid)
        return {"ok": True, "message": "Private draft archived; immutable run and publication provenance retained"}

    @app.get("/api/strategies/{sid}/versions")
    def versions(sid: str, user=Depends(current_user)):
        with db.connection() as conn:
            _owned(conn, "strategies", sid, user["id"], active=True)
            return [_version(row) for row in conn.execute("SELECT * FROM strategy_versions WHERE strategy_id=? ORDER BY number DESC", (sid,))]

    @app.post("/api/strategies/{sid}/versions", status_code=201)
    def snapshot(sid: str, user=Depends(require_csrf)):
        with db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            strategy = _owned(conn, "strategies", sid, user["id"], active=True)
            vid = _new_version(conn, sid, json.loads(strategy["spec_json"]))
            db.audit(conn, user["id"], "strategy.version_created", vid, {"strategy_id": sid})
            return _version(conn.execute("SELECT * FROM strategy_versions WHERE id=?", (vid,)).fetchone())

    @app.post("/api/strategies/{sid}/duplicate", status_code=201)
    def duplicate(sid: str, user=Depends(require_csrf)):
        with db.connection() as conn:
            row = _owned(conn, "strategies", sid, user["id"], active=True)
            copied = _new_strategy(conn, user["id"], row["name"] + " · copy", row["description"], json.loads(row["tags_json"]), json.loads(row["spec_json"]))
            db.audit(conn, user["id"], "strategy.duplicated", copied, {"source_id": sid})
            return _strategy(_owned(conn, "strategies", copied, user["id"], active=True))

    @app.post("/api/backtests", status_code=202)
    def launch(payload: BacktestInput, request: Request, user=Depends(require_csrf)):
        choices = {item["id"]: item for item in data.datasets()}
        if payload.dataset_id not in choices:
            raise HTTPException(422, "Unknown dataset")
        if choices[payload.dataset_id].get("status") == "unavailable":
            raise HTTPException(422, "The verified dataset is unavailable. Select a labelled demo explicitly; no automatic fallback is allowed.")
        jobs = request.app.state.jobs
        durable = job_mode == "durable"
        if not durable and not jobs.capacity.acquire(blocking=False):
            raise HTTPException(429, "The local queue is full (four jobs). Wait for a running job.")
        try:
            with db.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if durable and conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 4:
                    raise HTTPException(429, "The shared backtest queue is full (four admitted jobs).")
                strategy = _owned(conn, "strategies", payload.strategy_id, user["id"], active=True)
                if payload.version_id:
                    version = conn.execute("SELECT * FROM strategy_versions WHERE id=? AND strategy_id=?", (payload.version_id, payload.strategy_id)).fetchone()
                    if not version:
                        raise HTTPException(404, "Version not found")
                    spec = json.loads(version["spec_json"])
                    vid = version["id"]
                else:
                    spec = json.loads(strategy["spec_json"])
                    latest = conn.execute("SELECT * FROM strategy_versions WHERE id=?", (strategy["latest_version_id"],)).fetchone()
                    vid = latest["id"] if latest and latest["spec_json"] == encode(spec) else _new_version(conn, payload.strategy_id, spec)
                _require_valid(spec)
                if spec.get("schema_version") == 1 and (payload.config.execution_mode is not None or payload.config.availability_seconds is not None):
                    raise HTTPException(422, "Schema-one strategies preserve their original full-bar execution semantics; new execution modes require a new schema-two strategy.")
                if spec.get("symbol") != choices[payload.dataset_id].get("symbol") or spec.get("timeframe") != choices[payload.dataset_id].get("timeframe"):
                    raise HTTPException(422, "Strategy symbol/timeframe must match the dataset")
                job_id = identifier()
                conn.execute("INSERT INTO jobs (id,owner_id,strategy_id,version_id,dataset_id,config_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)", (job_id, user["id"], payload.strategy_id, vid, payload.dataset_id, encode(payload.config.model_dump(mode="json", exclude_none=True)), "queued", now()))
                db.audit(conn, user["id"], "backtest.queued", job_id, {"version_id": vid, "dataset_id": payload.dataset_id})
                if durable:
                    jobs.enqueue(conn, "backtest", job_id, user["id"])
                value = _job(_owned(conn, "jobs", job_id, user["id"]))
            if durable:
                jobs.dispatch_pending_sync(limit=1)
            else:
                jobs.pool.submit(jobs.execute, job_id)
            return value
        except BaseException:
            if not durable:
                jobs.capacity.release()
            raise

    @app.get("/api/jobs/{jid}")
    def job(jid: str, request: Request, user=Depends(current_user)):
        with db.connection() as conn:
            _owned(conn, "jobs", jid, user["id"])
        if job_mode == "durable":
            request.app.state.jobs.dispatch_pending_sync(limit=1)
        with db.connection() as conn:
            return _job(_owned(conn, "jobs", jid, user["id"]))

    @app.post("/api/jobs/{jid}/cancel")
    def cancel_queued_backtest(jid: str, user=Depends(require_csrf)):
        with db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = _owned(conn, "jobs", jid, user["id"])
            if row["status"] != "queued":
                raise HTTPException(409, "Only a queued candle job can be cancelled; running thread jobs cannot be forcibly stopped.")
            conn.execute("UPDATE jobs SET status='cancelled',error='Cancelled before execution.',finished_at=? WHERE id=?", (now(), jid))
            db.audit(conn, user["id"], "backtest.cancelled", jid)
            return _job(_owned(conn, "jobs", jid, user["id"]))

    @app.get("/api/backtests")
    def runs(user=Depends(current_user)):
        with db.connection() as conn:
            values = []
            for row in conn.execute("SELECT * FROM backtests WHERE owner_id=? ORDER BY created_at DESC,id LIMIT 200", (user["id"],)):
                value = _run(row)
                for key in ("equity", "trades", "monthly", "annual", "returns"):
                    value.pop(key, None)
                values.append(value)
            return values

    @app.get("/api/backtests/{rid}")
    def run(rid: str, user=Depends(current_user)):
        with db.connection() as conn:
            return _run(_owned(conn, "backtests", rid, user["id"]))

    @app.get("/api/backtests/{rid}/analysis")
    def analysis(rid: str, locale: str = Query(default="ru", pattern="^(ru|en)$"), user=Depends(current_user)):
        with db.connection() as conn:
            result = _run(_owned(conn, "backtests", rid, user["id"]))
        value = engine.explain_result(result, locale=locale)
        if not isinstance(value, dict):
            value = {"summary": str(value), "sections": []}
        value["mode"] = "offline_rules"
        value["provider_status"] = next(p for p in provider_statuses() if p["id"] == "analysis")
        return value

    @app.post("/api/community", status_code=201)
    def publish(payload: PublicationInput, request: Request, user=Depends(require_csrf)):
        with db.connection() as conn:
            _owned(conn, "strategies", payload.strategy_id, user["id"], active=True)
            run = dict(_owned(conn, "backtests", payload.run_id, user["id"]))
            if run["strategy_id"] != payload.strategy_id or run["version_id"] != payload.version_id or run["status"] != "succeeded":
                raise HTTPException(422, "Publication must match an actual completed run and its exact immutable version")
            version = conn.execute("SELECT * FROM strategy_versions WHERE id=? AND strategy_id=?", (payload.version_id, payload.strategy_id)).fetchone()
            if not version:
                raise HTTPException(404, "Version not found")
            spec_payload = version["spec_json"]
        dataset_metadata = json.loads(run["dataset_json"])
        replay = request.app.state.jobs.reproduce(json.loads(spec_payload), dataset_metadata["id"], json.loads(run["config_json"]))
        replay_payload = encode(replay)
        if replay_payload != run["result_json"]:
            raise HTTPException(409, "The exact version/dataset/config replay differs from the saved run. No reproducible publication was created. Run the saved version again and inspect provenance.")
        reproduction = {"status": "matched", "checked_at": now(), "result_sha256": sha256(replay_payload.encode("utf-8")).hexdigest(), "spec_sha256": replay.get("provenance", {}).get("spec_sha256"), "dataset_sha256": dataset_metadata.get("sha256"), "engine_version": replay.get("provenance", {}).get("engine_version"), "comparison": "canonical_complete_result_equality"}
        with db.connection() as conn:
            strategy = _owned(conn, "strategies", payload.strategy_id, user["id"], active=True)
            publication_id = identifier()
            metrics = json.loads(run["result_json"])["metrics"]
            conn.execute("INSERT INTO publications (id,owner_id,strategy_id,version_id,run_id,name,author,description,tags_json,spec_json,dataset_json,metrics_json,created_at,reproduction_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (publication_id, user["id"], payload.strategy_id, payload.version_id, payload.run_id, strategy["name"], user["name"], payload.description if payload.description is not None else strategy["description"], encode(payload.tags if payload.tags is not None else json.loads(strategy["tags_json"])), spec_payload, run["dataset_json"], encode(metrics), now(), encode(reproduction)))
            db.audit(conn, user["id"], "community.published", publication_id, {"run_id": payload.run_id, "version_id": payload.version_id, "reproduction": reproduction})
            return _publication(conn.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone(), True)

    @app.get("/api/community")
    def community():
        with db.connection() as conn:
            return [_publication(row) for row in conn.execute("SELECT * FROM publications ORDER BY created_at DESC,id LIMIT 200")]

    @app.get("/api/community/{pid}")
    def publication(pid: str):
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM publications WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, "Publication not found")
            value = _publication(row, True)
            run = conn.execute("SELECT result_json,config_json FROM backtests WHERE id=?", (row["run_id"],)).fetchone()
            value["result"] = json.loads(run["result_json"])
            value["config"] = json.loads(run["config_json"])
            return value

    @app.post("/api/community/{pid}/fork", status_code=201)
    def fork(pid: str, user=Depends(require_csrf)):
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM publications WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, "Publication not found")
            sid = _new_strategy(conn, user["id"], row["name"] + " · fork", row["description"], json.loads(row["tags_json"]), json.loads(row["spec_json"]), pid)
            db.audit(conn, user["id"], "community.forked", sid, {"publication_id": pid})
            return _strategy(_owned(conn, "strategies", sid, user["id"], active=True))

    @app.get("/api/news")
    def news(symbol: str = Query(default="BTCUSDT", pattern="^(BTCUSDT|ETHUSDT|SOLUSDT)$"), locale: str = Query(default="ru", pattern="^(ru|en)$")):
        return news_fixture(symbol, locale)

    @app.get("/api/ml")
    def ml(user=Depends(current_user)):
        with db.connection() as conn:
            drafts = [{"id": row["id"], "name": row["name"], "config": json.loads(row["config_json"]), "created_at": row["created_at"]} for row in conn.execute("SELECT * FROM ml_drafts WHERE owner_id=? ORDER BY created_at DESC LIMIT 100", (user["id"],))]
        return {"status": "local_bounded_worker", "capabilities": ["save_research_draft", "logistic_direction", "ridge_return", "chronological_evaluation", "native_model_registry"], "training_enabled": True, "drafts": drafts}

    @app.post("/api/ml/drafts", status_code=201)
    def ml_draft(payload: MLDraftInput, user=Depends(require_csrf)):
        if len(encode(payload.config)) > 20_000:
            raise HTTPException(413, "Draft configuration too large")
        did, stamp = identifier(), now()
        with db.connection() as conn:
            conn.execute("INSERT INTO ml_drafts VALUES (?,?,?,?,?)", (did, user["id"], payload.name, encode(payload.config), stamp))
            db.audit(conn, user["id"], "ml.draft_saved", did, {"training_started": False})
        return {"id": did, "name": payload.name, "config": payload.config, "created_at": stamp, "status": "draft_only", "training_started": False}

    @app.post("/api/ai/generate")
    def generate(payload: GenerationRequest, user=Depends(require_csrf)):
        raise HTTPException(503, "This legacy unscoped generation endpoint is disabled. Use a strategy-scoped copilot conversation with explicit external-data consent and proposal approval, or use the local editor.")

    @app.get("/api/bots")
    def bots(user=Depends(current_user)):
        return {"status": "preview_only", "bots": [], "execution_enabled": False, "paper_trading_enabled": False, "message": "No exchange connection or paper-fill engine is running. Saved strategies are research only."}

    @app.get("/api/audit")
    def audit(user=Depends(current_user)):
        with db.connection() as conn:
            return [{"id": row["id"], "action": row["action"], "entity_id": row["entity_id"], "details": json.loads(row["details_json"]), "created_at": row["created_at"]} for row in conn.execute("SELECT * FROM audit_events WHERE owner_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (user["id"],))]

    @app.get("/api/dashboard")
    def dashboard(user=Depends(current_user)):
        with db.connection() as conn:
            counts = {"strategies": conn.execute("SELECT COUNT(*) FROM strategies WHERE owner_id=? AND deleted_at IS NULL", (user["id"],)).fetchone()[0], "backtests": conn.execute("SELECT COUNT(*) FROM backtests WHERE owner_id=?", (user["id"],)).fetchone()[0], "publications": conn.execute("SELECT COUNT(*) FROM publications WHERE owner_id=?", (user["id"],)).fetchone()[0]}
            recent = [{"id": row["id"], "strategy_id": row["strategy_id"], "metrics": json.loads(row["result_json"])["metrics"], "dataset": json.loads(row["dataset_json"]), "created_at": row["created_at"]} for row in conn.execute("SELECT * FROM backtests WHERE owner_id=? ORDER BY created_at DESC LIMIT 5", (user["id"],))]
        return {"counts": counts, "recent_runs": recent, "live_balance": None, "active_bots": 0, "mode": "local_research"}

    copilot.register_routes(app, db, (_owned, _new_version))
    research.register_routes(app, db, (_owned, _new_version, _require_valid, BacktestConfig))
    app.include_router(market_router)
    return app


app = create_app()
