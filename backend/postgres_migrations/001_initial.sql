-- PostgreSQL schema for the shared hosted database. No local data is copied.
CREATE FUNCTION kedr_nocase(value TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$ SELECT translate(value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') $$;
CREATE FUNCTION kedr_json_valid(value TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
BEGIN
 PERFORM value::json;
 RETURN TRUE;
EXCEPTION WHEN invalid_text_representation THEN RETURN FALSE;
END;
$$;
CREATE FUNCTION kedr_reject_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'immutable database record' USING ERRCODE = '23514';
END;
$$;
CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL, password_hash TEXT,
 name TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'beginner', locale TEXT NOT NULL DEFAULT 'ru',
 timezone TEXT NOT NULL DEFAULT 'Europe/Moscow', theme TEXT NOT NULL DEFAULT 'dark',
 is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX users_email_nocase ON users(kedr_nocase(email));
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf_token TEXT NOT NULL, expires_at BIGINT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE strategies (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', tags_json TEXT NOT NULL DEFAULT '[]', spec_json TEXT NOT NULL,
 latest_version_id TEXT, version_number INTEGER NOT NULL DEFAULT 0,
 forked_from TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX strategies_owner ON strategies(owner_id, updated_at);
CREATE TABLE strategy_versions (
 id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id), number INTEGER NOT NULL,
 spec_json TEXT NOT NULL, spec_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(strategy_id, number)
);
CREATE TRIGGER strategy_versions_immutable_update BEFORE UPDATE ON strategy_versions
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TRIGGER strategy_versions_immutable_delete BEFORE DELETE ON strategy_versions
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), strategy_id TEXT NOT NULL REFERENCES strategies(id),
 version_id TEXT NOT NULL REFERENCES strategy_versions(id), dataset_id TEXT NOT NULL,
 config_json TEXT NOT NULL, status TEXT NOT NULL, error TEXT, run_id TEXT,
 created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
CREATE INDEX jobs_owner ON jobs(owner_id, created_at);
CREATE TABLE backtests (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), strategy_id TEXT NOT NULL REFERENCES strategies(id),
 version_id TEXT NOT NULL REFERENCES strategy_versions(id), dataset_json TEXT NOT NULL,
 config_json TEXT NOT NULL, result_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'succeeded', created_at TEXT NOT NULL
);
CREATE INDEX backtests_owner ON backtests(owner_id, created_at);
CREATE TRIGGER backtests_immutable_update BEFORE UPDATE ON backtests
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TRIGGER backtests_immutable_delete BEFORE DELETE ON backtests
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TABLE publications (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), strategy_id TEXT NOT NULL REFERENCES strategies(id),
 version_id TEXT NOT NULL REFERENCES strategy_versions(id), run_id TEXT NOT NULL REFERENCES backtests(id),
 name TEXT NOT NULL, author TEXT NOT NULL, description TEXT NOT NULL, tags_json TEXT NOT NULL,
 spec_json TEXT NOT NULL, dataset_json TEXT NOT NULL, metrics_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX publications_created ON publications(created_at);
CREATE TRIGGER publications_immutable_update BEFORE UPDATE ON publications
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TRIGGER publications_immutable_delete BEFORE DELETE ON publications
FOR EACH ROW EXECUTE FUNCTION kedr_reject_immutable();
CREATE TABLE audit_events (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL,
 entity_id TEXT, details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX audit_owner ON audit_events(owner_id, created_at);
CREATE TABLE ml_drafts (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 config_json TEXT NOT NULL, created_at TEXT NOT NULL
);
