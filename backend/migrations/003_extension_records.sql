-- Extension records are schema foundations, not active external integrations.
CREATE TABLE dataset_references (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
 source_type TEXT NOT NULL CHECK(source_type IN ('verified_historical','synthetic_demo','external','incomplete')),
 content_sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
 created_at TEXT NOT NULL, UNIQUE(provider, content_sha256)
);
CREATE TABLE analysis_reports (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), run_id TEXT NOT NULL REFERENCES backtests(id),
 mode TEXT NOT NULL CHECK(mode IN ('offline_rules','external_ai')), provider TEXT NOT NULL, template_version TEXT NOT NULL,
 evidence_hash TEXT NOT NULL, report_json TEXT NOT NULL CHECK(json_valid(report_json)), created_at TEXT NOT NULL
);
CREATE INDEX analysis_owner_run ON analysis_reports(owner_id,run_id);
CREATE TABLE ml_experiments (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','queued','running','failed','succeeded')) DEFAULT 'draft',
 target_json TEXT NOT NULL CHECK(json_valid(target_json)), feature_schema_json TEXT NOT NULL CHECK(json_valid(feature_schema_json)),
 dataset_id TEXT REFERENCES dataset_references(id), chronological_split_json TEXT NOT NULL CHECK(json_valid(chronological_split_json)),
 model_version TEXT, resource_budget_json TEXT NOT NULL CHECK(json_valid(resource_budget_json)),
 result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)), created_at TEXT NOT NULL
);
CREATE TABLE news_articles (
 id TEXT PRIMARY KEY, source_url TEXT NOT NULL, source_name TEXT NOT NULL,
 title TEXT NOT NULL, published_at TEXT NOT NULL, first_seen_at TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, assets_json TEXT NOT NULL CHECK(json_valid(assets_json)),
 is_fixture INTEGER NOT NULL DEFAULT 0 CHECK(is_fixture IN (0,1)), UNIQUE(source_url,content_sha256)
);
CREATE TABLE sentiment_observations (
 id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES news_articles(id), observed_at TEXT NOT NULL,
 provider TEXT NOT NULL, model_version TEXT NOT NULL, label TEXT NOT NULL CHECK(label IN ('positive','negative','neutral')),
 score REAL CHECK(score IS NULL OR (score>=-1 AND score<=1)),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json))
);
CREATE TABLE integration_configurations (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), provider_kind TEXT NOT NULL,
 provider_name TEXT NOT NULL, public_configuration_json TEXT NOT NULL CHECK(json_valid(public_configuration_json)),
 secret_reference_name TEXT, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), created_at TEXT NOT NULL,
 UNIQUE(owner_id,provider_kind,provider_name)
);
CREATE TABLE moderation_reports (
 id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL REFERENCES users(id), publication_id TEXT NOT NULL REFERENCES publications(id),
 reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reviewed','closed')), created_at TEXT NOT NULL
);
