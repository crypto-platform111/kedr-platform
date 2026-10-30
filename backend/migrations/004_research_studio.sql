-- Additive studio records. Existing users, versions, runs and publications remain untouched.
CREATE TABLE copilot_conversations (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), strategy_id TEXT NOT NULL REFERENCES strategies(id),
 title TEXT NOT NULL, locale TEXT NOT NULL CHECK(locale IN ('ru','en')), created_at TEXT NOT NULL
);
CREATE INDEX copilot_owner ON copilot_conversations(owner_id,strategy_id,created_at);
CREATE TABLE copilot_messages (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES copilot_conversations(id),
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, mode TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE copilot_proposals (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), conversation_id TEXT NOT NULL REFERENCES copilot_conversations(id),
 strategy_id TEXT NOT NULL REFERENCES strategies(id), before_spec_json TEXT NOT NULL, before_spec_hash TEXT NOT NULL,
 proposed_spec_json TEXT NOT NULL, proposed_spec_hash TEXT NOT NULL, diff_json TEXT NOT NULL, validation_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','approved','rolled_back','rejected')), approved_version_id TEXT,
 created_at TEXT NOT NULL, applied_at TEXT
);
CREATE TRIGGER copilot_proposal_payload_immutable BEFORE UPDATE OF before_spec_json,before_spec_hash,proposed_spec_json,proposed_spec_hash,diff_json,validation_json ON copilot_proposals BEGIN SELECT RAISE(ABORT, 'immutable proposal payload'); END;
CREATE TABLE ai_usage (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), day TEXT NOT NULL, status TEXT NOT NULL,
 reserved_tokens INTEGER NOT NULL, accounted_tokens INTEGER NOT NULL, reserved_usd REAL NOT NULL, accounted_usd REAL NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX ai_usage_owner_day ON ai_usage(owner_id,day);
CREATE TABLE chart_preferences (
 owner_id TEXT NOT NULL REFERENCES users(id), preference_key TEXT NOT NULL, preferences_json TEXT NOT NULL,
 updated_at TEXT NOT NULL, PRIMARY KEY(owner_id,preference_key)
);
CREATE TABLE research_jobs (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL CHECK(kind IN ('ml','scenarios')),
 name TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 configuration_json TEXT NOT NULL, result_json TEXT, error TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
CREATE INDEX research_jobs_owner ON research_jobs(owner_id,created_at);
CREATE TABLE model_registry (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), experiment_id TEXT NOT NULL REFERENCES research_jobs(id),
 model_family TEXT NOT NULL, artifact_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER model_registry_immutable_update BEFORE UPDATE ON model_registry BEGIN SELECT RAISE(ABORT, 'immutable model artifact'); END;
CREATE TRIGGER model_registry_immutable_delete BEFORE DELETE ON model_registry BEGIN SELECT RAISE(ABORT, 'immutable model artifact'); END;
