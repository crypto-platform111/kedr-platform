-- Shared hosted authentication admission; no raw IP, email or credential data.
CREATE TABLE auth_attempts (
 id TEXT PRIMARY KEY,
 bucket_key TEXT NOT NULL,
 attempted_at DOUBLE PRECISION NOT NULL,
 expires_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX auth_attempts_bucket_time ON auth_attempts(bucket_key,attempted_at);
CREATE INDEX auth_attempts_expiry ON auth_attempts(expires_at);
