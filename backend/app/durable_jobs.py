"""Shared-database work claims and a transactional Vercel Queues outbox.

The request commits its job and outbox row together. Publishing may fail without
losing the admitted job; a protected scheduled invocation dispatches pending and
stale work. Queue delivery is at least once. A lease token fences *all* completion
writes, so duplicate deliveries, instance death and owner cancellation cannot
create a second saved run or model. No post-response worker thread is used.

The production Database adapter serializes short database transactions across
instances. Expensive computation and network publishing never hold that lock.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import inspect
import json
import logging
import threading
import uuid

import anyio

from . import data, engine
from .db import encode, identifier, now
from .process_runner import ProcessRunner


log = logging.getLogger("kedr.durable_jobs")
TOPIC = "kedr-research-work"
LEASE_SECONDS = 600
OUTBOX_LEASE_SECONDS = 60
RECOVERY_SECONDS = 900
MAX_ATTEMPTS = 5
MAX_RESULT_BYTES = 3_000_000
_NAMESPACE = uuid.UUID("8fece669-2f7c-4686-bb75-367e546246a8")


class WorkBusy(RuntimeError):
    """Delivery must retry: another live claim owns this work."""


@dataclass(frozen=True)
class Claim:
    work_key: str
    kind: str
    job_id: str
    owner_id: str
    token: str
    attempt: int


def _after(stamp: str, seconds: int) -> str:
    value = datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _table(kind):
    if kind not in ("backtest", "research"):
        raise ValueError("Unsupported durable work type")
    return "jobs" if kind == "backtest" else "research_jobs"


class QueuePublisher:
    """Lazy import keeps local SQLite installs independent of queue credentials."""

    async def __call__(self, payload, idempotency_key):
        from vercel.queue import send

        # Only a random work reference is sent, not a dataset, model or identity.
        return await send(TOPIC, payload, idempotency_key=idempotency_key, retention=86400)


class DurableJobs:
    def __init__(self, db, *, publisher=None, clock=None, compute=None):
        self.db = db
        self.publisher = publisher or QueuePublisher()
        self.clock = clock or now
        self.compute = compute or self._compute
        self.runner = ProcessRunner()
        # Compatibility with local cancellation routes. This is not a shared
        # distributed lock; SQL state and lease fencing provide that boundary.
        self.lifecycle_lock = threading.Lock()

    def close(self):
        # A web instance shutdown must not cancel work in another invocation.
        # Worker children are supervised synchronously by ProcessRunner.run().
        pass

    def enqueue(self, conn, kind, job_id, owner_id, payload=None):
        """Call inside the transaction that creates the actual application job."""
        _table(kind)
        stamp = self.clock()
        key = f"{kind}:{job_id}"
        encoded = encode(payload or {})
        if len(encoded.encode()) > 16384:
            raise ValueError("Durable job reference payload exceeds its fixed limit")
        conn.execute(
            "INSERT INTO durable_work (work_key,kind,job_id,owner_id,status,available_at,payload_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(kind,job_id) DO NOTHING",
            (key, kind, job_id, owner_id, "queued", stamp, encoded, stamp, stamp),
        )
        return key

    def _recover(self, conn, stamp):
        """Re-arm stale queue delivery without changing another live claim."""
        conn.execute(
            "UPDATE durable_work SET outbox_pending=1,outbox_lease_token=NULL,outbox_lease_until=NULL "
            "WHERE status IN ('queued','running') AND outbox_pending=0 AND "
            "((status='running' AND lease_until<=?) OR (status='queued' AND updated_at<=?))",
            (stamp, _after(stamp, -RECOVERY_SECONDS)),
        )

    async def dispatch_pending(self, limit=20):
        """Publish a bounded batch. Return counts only; never leak SDK errors."""
        if not 1 <= limit <= 100:
            raise ValueError("Outbox dispatch limit must be between one and 100")
        stamp = self.clock()
        with self.db.connection() as conn:
            self._recover(conn, stamp)
            keys = [r[0] for r in conn.execute(
                "SELECT work_key FROM durable_work WHERE status IN ('queued','running') AND outbox_pending=1 "
                "AND available_at<=? AND (outbox_lease_until IS NULL OR outbox_lease_until<=?) "
                "ORDER BY created_at,work_key LIMIT ?", (stamp, stamp, limit),
            )]
        published = failed = 0
        for key in keys:
            token, stamp = identifier(), self.clock()
            with self.db.connection() as conn:
                changed = conn.execute(
                    "UPDATE durable_work SET outbox_lease_token=?,outbox_lease_until=?,dispatch_count=dispatch_count+1 "
                    "WHERE work_key=? AND status IN ('queued','running') AND outbox_pending=1 "
                    "AND (outbox_lease_until IS NULL OR outbox_lease_until<=?)",
                    (token, _after(stamp, OUTBOX_LEASE_SECONDS), key, stamp),
                ).rowcount
                if not changed:
                    continue
                generation = conn.execute("SELECT dispatch_count FROM durable_work WHERE work_key=?", (key,)).fetchone()[0]
            try:
                message_id = self.publisher({"work_key": key}, f"{key}:{generation}")
                if inspect.isawaitable(message_id):
                    message_id = await message_id
                # SDK None means accepted deferred ingestion, not send failure.
                with self.db.connection() as conn:
                    conn.execute(
                        "UPDATE durable_work SET outbox_pending=0,outbox_lease_token=NULL,outbox_lease_until=NULL,"
                        "queue_message_id=?,updated_at=? WHERE work_key=? AND outbox_lease_token=?",
                        (str(message_id) if message_id is not None else None, self.clock(), key, token),
                    )
                published += 1
            except Exception:
                # Never log the SDK exception: it can contain auth headers/URLs.
                failed += 1
                log.warning("Queue publication deferred for durable work %s", key)
                with self.db.connection() as conn:
                    conn.execute(
                        "UPDATE durable_work SET outbox_lease_token=NULL,outbox_lease_until=NULL,last_error=? "
                        "WHERE work_key=? AND outbox_lease_token=?",
                        ("Queue delivery is pending; the scheduled dispatcher will retry.", key, token),
                    )
        return {"published": published, "deferred": failed}

    def dispatch_pending_sync(self, limit=20):
        """Use from synchronous FastAPI endpoints, outside their DB transaction."""
        return asyncio.run(self.dispatch_pending(limit))

    def claim(self, work_key):
        stamp, token = self.clock(), identifier()
        with self.db.connection() as conn:
            changed = conn.execute(
                "UPDATE durable_work SET status='running',attempt=attempt+1,lease_token=?,lease_until=?,updated_at=? "
                "WHERE work_key=? AND attempt<? AND ((status='queued' AND available_at<=?) "
                "OR (status='running' AND lease_until<=?))",
                (token, _after(stamp, LEASE_SECONDS), stamp, work_key, MAX_ATTEMPTS, stamp, stamp),
            ).rowcount
            row = conn.execute("SELECT * FROM durable_work WHERE work_key=?", (work_key,)).fetchone()
            if row is None or row["status"] in ("succeeded", "failed", "cancelled"):
                return None
            if not changed:
                eligible = (row["status"] == "queued" and row["available_at"] <= stamp or
                            row["status"] == "running" and row["lease_until"] <= stamp)
                if eligible and row["attempt"] >= MAX_ATTEMPTS:
                    self._terminal(conn, row, "failed", "Hosted execution exhausted its fixed retry limit.", stamp)
                    return None
                raise WorkBusy("Durable work has an active lease or a pending retry delay")
            entity = conn.execute(
                f"SELECT status FROM {_table(row['kind'])} WHERE id=? AND owner_id=?",
                (row["job_id"], row["owner_id"]),
            ).fetchone()
            if entity is None or entity[0] not in ("queued", "running"):
                terminal = entity[0] if entity is not None and entity[0] in ("succeeded", "cancelled") else "failed"
                self._terminal(conn, row, terminal, "Work was already completed, cancelled or unavailable.", stamp)
                return None
            conn.execute(
                f"UPDATE {_table(row['kind'])} SET status='running',started_at=COALESCE(started_at,?),error=NULL WHERE id=?",
                (stamp, row["job_id"]),
            )
            return Claim(work_key, row["kind"], row["job_id"], row["owner_id"], token, row["attempt"])

    def _terminal(self, conn, row, status, message, stamp):
        conn.execute(
            "UPDATE durable_work SET status=?,last_error=?,lease_token=NULL,lease_until=NULL,outbox_pending=0,updated_at=? WHERE work_key=?",
            (status, message, stamp, row["work_key"]),
        )
        if status == "failed":
            conn.execute(
                f"UPDATE {_table(row['kind'])} SET status='failed',error=?,finished_at=? WHERE id=? AND status IN ('queued','running')",
                (message, stamp, row["job_id"]),
            )

    def _fenced(self, conn, claim):
        row = conn.execute("SELECT * FROM durable_work WHERE work_key=?", (claim.work_key,)).fetchone()
        if not row or row["status"] != "running" or row["lease_token"] != claim.token or row["lease_until"] <= self.clock():
            return None
        entity = conn.execute(
            f"SELECT status FROM {_table(claim.kind)} WHERE id=? AND owner_id=?", (claim.job_id, claim.owner_id),
        ).fetchone()
        if not entity or entity[0] != "running":
            status = "cancelled" if entity and entity[0] == "cancelled" else "failed"
            self._terminal(conn, row, status, "Owner cancellation or missing job suppressed completion.", self.clock())
            return None
        return row

    def _compute(self, claim):
        with self.db.connection() as conn:
            row = dict(conn.execute(f"SELECT * FROM {_table(claim.kind)} WHERE id=?", (claim.job_id,)).fetchone())
            if claim.kind == "backtest":
                version = conn.execute("SELECT spec_json FROM strategy_versions WHERE id=?", (row["version_id"],)).fetchone()
                spec = json.loads(version[0])
        if claim.kind == "backtest":
            dataset = data.load_dataset_for_strategy(spec, row["dataset_id"])
            return {"result": engine.run_backtest(spec, dataset, json.loads(row["config_json"])), "dataset": dataset["metadata"]}
        from .research import _step, scenarios

        config = json.loads(row["configuration_json"])
        if row["kind"] == "ml":
            dataset = data.load_dataset(config["dataset_id"])
            if len(dataset["bars"]) > 20000:
                raise ValueError("The bounded ML worker accepts at most 20,000 candles")
            config["step_ms"] = _step(dataset["metadata"])
            payload = {"bars": dataset["bars"], "dataset": dataset["metadata"], "provenance": dataset.get("provenance", {}), "config": config}
            output, resources = self.runner.run(claim.job_id, encode(payload).encode())
            result = json.loads(output)
            result["resources"] = resources
        else:
            dataset = data.load_dataset_for_strategy(config["spec"], config["dataset_id"])
            result = scenarios(config["spec"], dataset, config["config"], config["scenario_kind"])
            result["dataset"] = dataset["metadata"]
        return {"result": result}

    def complete(self, claim, output):
        result = output["result"]
        encoded, stamp = encode(result), self.clock()
        if claim.kind == "research" and len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError("Saved result exceeds its fixed 3 MB artifact limit")
        with self.db.connection() as conn:
            if self._fenced(conn, claim) is None:
                return False
            row = dict(conn.execute(f"SELECT * FROM {_table(claim.kind)} WHERE id=?", (claim.job_id,)).fetchone())
            if claim.kind == "backtest":
                run_id = uuid.uuid5(_NAMESPACE, claim.work_key).hex
                conn.execute("INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?)", (
                    run_id, row["owner_id"], row["strategy_id"], row["version_id"], encode(output["dataset"]), row["config_json"], encoded, "succeeded", stamp,
                ))
                conn.execute("UPDATE jobs SET status='succeeded',run_id=?,finished_at=?,error=NULL WHERE id=?", (run_id, stamp, claim.job_id))
                self.db.audit(conn, row["owner_id"], "backtest.completed", run_id, {"version_id": row["version_id"], "dataset_id": row["dataset_id"]})
            else:
                if row["kind"] == "ml":
                    config = json.loads(row["configuration_json"])
                    artifact = encode(result["artifact"])
                    model_id = uuid.uuid5(_NAMESPACE, claim.work_key).hex
                    conn.execute("INSERT INTO model_registry VALUES (?,?,?,?,?,?,?)", (
                        model_id, row["owner_id"], claim.job_id, config["model_family"], artifact, sha256(artifact.encode()).hexdigest(), stamp,
                    ))
                    encoded = encode({**result, "model_id": model_id})
                    if len(encoded.encode()) > MAX_RESULT_BYTES:
                        raise ValueError("Saved result exceeds its fixed 3 MB artifact limit")
                conn.execute("UPDATE research_jobs SET status='succeeded',result_json=?,finished_at=?,error=NULL WHERE id=?", (encoded, stamp, claim.job_id))
                self.db.audit(conn, row["owner_id"], "research.completed", claim.job_id, {"kind": row["kind"], "result_sha256": sha256(encoded.encode()).hexdigest()})
            conn.execute(
                "UPDATE durable_work SET status='succeeded',lease_token=NULL,lease_until=NULL,outbox_pending=0,last_error=NULL,updated_at=? WHERE work_key=? AND lease_token=?",
                (stamp, claim.work_key, claim.token),
            )
        return True

    def fail(self, claim, *, permanent=False):
        stamp = self.clock()
        with self.db.connection() as conn:
            row = self._fenced(conn, claim)
            if row is None:
                return False
            if permanent or claim.attempt >= MAX_ATTEMPTS:
                message = "Hosted execution failed its input/resource checks." if permanent else "Hosted execution exhausted its fixed retry limit."
                self._terminal(conn, row, "failed", message, stamp)
                self.db.audit(conn, claim.owner_id, f"{claim.kind}.failed", claim.job_id, {"error": message})
                return False
            conn.execute(
                "UPDATE durable_work SET status='queued',lease_token=NULL,lease_until=NULL,outbox_pending=1,available_at=?,"
                "updated_at=?,last_error=? WHERE work_key=? AND lease_token=?",
                (_after(stamp, min(300, 30 * 2 ** (claim.attempt - 1))), stamp, "Interrupted execution will retry within its fixed attempt budget.", claim.work_key, claim.token),
            )
            conn.execute(f"UPDATE {_table(claim.kind)} SET status='queued',error=NULL WHERE id=?", (claim.job_id,))
        return True

    async def handle(self, work_key):
        claim = self.claim(work_key)
        if claim is None:
            return "already_terminal"
        try:
            # Await work for the entire queue invocation. A synchronous engine
            # uses a request-bound worker thread so the SDK can renew its queue
            # lease on the event loop. Nothing is scheduled after the response;
            # the subscriber cannot acknowledge before computation and the
            # fenced database commit finish. Keep cancellation non-abandoning.
            if inspect.iscoroutinefunction(self.compute):
                output = await self.compute(claim)
            else:
                output = await anyio.to_thread.run_sync(self.compute, claim, abandon_on_cancel=False)
            if inspect.isawaitable(output):
                output = await output
            return "succeeded" if self.complete(claim, output) else "completion_suppressed"
        except ValueError:
            self.fail(claim, permanent=True)
            return "failed"
        except Exception:
            retry = self.fail(claim)
            log.warning("Durable %s execution interrupted at attempt %d", claim.kind, claim.attempt)
            if retry:
                # Avoid carrying exception text that might contain DSNs/secrets.
                raise WorkBusy("Durable execution scheduled for retry") from None
            return "failed"

    def reproduce(self, spec, dataset_id, config):
        """Request-bound exact replay; failure never creates a publication.

        This preserves the existing publication contract. It is intentionally
        not advertised as an asynchronous durable job. A terminated request
        creates no publication and the owner can retry the request.
        """
        dataset = data.load_dataset_for_strategy(spec, dataset_id)
        return engine.run_backtest(spec, dataset, config)
