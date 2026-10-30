-- Durable hosted work/outbox metadata. Local thread workers do not use this table.
-- Payloads contain immutable application references, never provider credentials.
CREATE TABLE durable_work (
 work_key TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('backtest','research')),
 job_id TEXT NOT NULL,
 owner_id TEXT NOT NULL REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT,
 lease_until TEXT,
 available_at TEXT NOT NULL,
 outbox_pending INTEGER NOT NULL DEFAULT 1,
 outbox_lease_token TEXT,
 outbox_lease_until TEXT,
 dispatch_count INTEGER NOT NULL DEFAULT 0,
 queue_message_id TEXT,
 last_error TEXT,
 payload_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(kind,job_id)
);
CREATE INDEX durable_work_outbox ON durable_work(status,outbox_pending,available_at);
CREATE INDEX durable_work_owner ON durable_work(owner_id,status);
