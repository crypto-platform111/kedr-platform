# Local deployment and production path

For the implemented two-service Vercel configuration, shared PostgreSQL adapter and durable queue worker, see [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md). The sections below describe SQLite/local mode unless explicitly noted; do not apply its single-process startup recovery to hosted mode.

Run the checkout from any writable directory as the current ordinary Windows user. Follow README.md to install Python/Node and initialize the environment. No personal drive layout or original research checkout is required for the labelled demo workflow. The application does not stop or reconfigure unrelated processes.

## Start and verify locally

After the environment and frontend dependencies documented in README are installed:

```powershell
Set-Location -LiteralPath 'C:\path\to\kedr-platform'
.\scripts\start.ps1
```

Open **http://127.0.0.1:5173**. The web server proxies `/api` to **http://127.0.0.1:8710**. Keep the same browser host consistently: `localhost` and `127.0.0.1` are distinct cookie origins.

The launcher checks both ports before starting. It refuses to stop an unknown listener and records only its own process IDs under `data\runtime`. Startup succeeds only after both API health and the web root respond. Verify them independently when diagnosing startup:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8710/api/health'
Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing
```

The direct backend command, useful for diagnosis, is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8710
```

Do not run this together with an already running launcher instance. A successful health response confirms API readiness; it does not prove that a research job completed. Create a strategy, run it, poll its job to `succeeded`, reopen the persisted result and inspect its dataset/provenance to verify the full workflow.

After a successful frontend build, `scripts\start.ps1 -Production` selects Vite's **local preview** mode on the same loopback port. The switch name does not make Vite preview an internet production server.

Stop only the processes recorded for this project:

```powershell
.\scripts\stop.ps1
```

The stop helper checks the process executable's project containment before stopping it. It does not target the old collector or other services. API and web logs live under `data\runtime` in the project directory. Avoid copying private logs to public bug reports.

## Environment configuration

The launcher reads this project's optional `.env` into its child process environment. Importing the backend directly does not load `.env` automatically; set variables in the calling process if not using the launcher. Do not point writable platform storage at any legacy study or market database.

| Variable | Implemented behavior |
| --- | --- |
| `KEDR_DATA_DIR` | SQLite directory; defaults to the checkout's `data` directory. A relative path resolves against the process working directory. |
| `KEDR_SECURE_COOKIES` | Exact value `1` sets the session cookie's `Secure` flag. Default/local HTTP uses `0`. Enable only with a properly configured HTTPS endpoint. |
| `KEDR_ALLOWED_HOSTS` | Optional comma-separated additional host names. The defaults remain `127.0.0.1`, `localhost`, `testserver`. This does not change binding or the CORS allowlist. |
| `KEDR_LEGACY_ROOT` | Optional read-only location of a separately installed verified archive inventory. Blank means unconfigured: historical datasets are explicitly unavailable. The adapter enforces its allow-listed 2022–2025 ZIP source containment; no old database or runner is opened. Select labelled synthetic demo datasets on a normal clone. |
| `KEDR_AI_PROVIDER`, `KEDR_AI_API_KEY`, `KEDR_AI_MODEL` | The optional OpenAI adapter requires explicit configuration, valid budget/rate settings and per-message consent before a request. Blank keys/models leave it disconnected. Key values are never returned. See AI_INTEGRATION.md. |
| `KEDR_NEWS_API_KEY`, sentiment/training service settings | These interface placeholders do not activate live news, remote training or exchange execution. Native bounded local logistic/ridge research uses no remote training service. |

Keep `.env` and runtime data private. Never place secrets in frontend source or `VITE_` variables. This application accepts no live exchange credentials.

## Persistence and migrations

The API automatically applies new files from `backend/migrations` in filename order. It records applied filenames in `schema_migrations`. Already applied migration files are not rerun; add a new migration instead of editing historical SQL. Each migration and its registration use a SQLite transaction. Keep a consistent backup before changing the schema.

SQLite is configured with foreign keys, a 15-second busy timeout and WAL journaling. The backend opens short-lived connections per operation. Jobs, immutable versions, results, publications, user/session records and audit events persist in `platform.sqlite3`. Result equity/trades are part of the sealed result JSON. Additional schema-foundation tables may exist for future services; their presence is not evidence that an AI/news/ML integration is active.

A publication with `reproducible_snapshot` has passed a fresh deterministic replay using the exact saved version, dataset and configuration, with equality of the complete canonical engine result. The replay evidence is saved on the publication. An old publication without that evidence remains a `saved_snapshot`; it is never upgraded by a schema migration or by a UI label. Engine changes can legitimately make replay differ, in which case the server refuses the new publication until a new matching run is produced. No old result is rewritten.

Use SQLite's backup API for live backups. For a stopped application, copy the complete consistent database state; copying only the database while WAL writes are active is unsafe. Restore to a separate directory first, select it with `KEDR_DATA_DIR`, then verify login, strategy versions, saved results, publications and migrations. Do not test restores over the only copy of private work.

## Worker behavior and capacity

Use **one Uvicorn worker process**. This release has one in-process thread executing backtests/publication replays and a four-task admission cap. Extra work receives HTTP 429. A publication replay has a 60-second request wait ceiling; after a timeout its bounded task may still finish, but no publication is created for that request. There is no hard thread cancellation.

On application startup, previously `queued` or `running` backtest records are marked `failed` with an interruption explanation. They are not automatically executed again. Completed results survive restart. Normal application shutdown waits for admitted worker tasks to finish; forcibly stopping a process can interrupt them. The UI must show the persisted failure and let the user submit a new job rather than pretend a result exists.

Requests are restricted to 200,000 actual streamed bytes, and strategy graphs to 150,000 canonical JSON characters/80 nodes/150 edges. The engine accepts at most 20,000 candles per job and the public API restricts date selections to before 2026. Execution delays are 1–6, with delay 1 meaning a completed signal bar followed by a full intervening candle, then execution at open `i+2`. No signal-close fill is used.

These are per-process engineering bounds, not a hosted-service resource policy. There is no deployment-wide storage accounting or durable distributed queue system. The optional AI adapter separately applies its configured local usage budgets, and the local ML subprocess has bounded time/resources. Neither replaces a hosted resource policy. Monitor the data directory's growth. A second API process must not be added as a substitute for a durable queue design.

## PostgreSQL hosting and further operational hardening

The optional hosted implementation now uses a **new platform** PostgreSQL database and a transactional queue outbox. Never attach or migrate the existing trading/research databases. Preserve stable user/strategy/version/run/publication identifiers, canonical spec/config/result hashes, foreign-key relationships and replay provenance. Replace SQLite-specific SQL/triggers with explicit PostgreSQL migrations and equivalent immutable-record enforcement. JSON result records can initially map to JSONB; larger sealed artifacts can later move to versioned object storage with content hashes and ownership checks.

Test the move on a consistent restored snapshot. Compare record counts and hashes, then exercise two-user ownership, CSRF/session expiry, version immutability, completed-job recovery, publication replay and public/private boundaries against the new backend. Verify all dates/numbers remain unchanged. Keep a rollback-ready untouched SQLite backup and avoid serving two writable databases as independent authorities.

The hosted path implements database-backed admission, durable job references, fenced leases, bounded retries and idempotent result publication. Additional production policies for per-user CPU/storage quotas and retention remain operator responsibilities. Run CPU work in constrained worker processes or containers with real time/memory limits. Include engine version and dataset hash in the envelope, and separate worker credentials from the web service. Do not enable ML training or exchange execution merely by changing a worker flag.

## Public hosting prerequisites

Replace the development/preview server with a built static frontend behind a configured reverse proxy, and keep API/worker/database ports private. Add TLS, secure cookies, an exact production host/origin policy, tested forwarded-header trust, request limits at the proxy and a content-security policy. Add account verification/recovery, revocable sessions, distributed abuse controls, operational metrics, backups with tested restores, dependency/security review, and a documented retention/deletion policy before accepting public users.

AI is disconnected by default; the implemented optional OpenAI adapter requires explicit configuration, consent, bounded requests, validated proposals, approval and budgets. Live news/sentiment feeds and remote training services remain disconnected. Hosted integrations need provider-specific health checks, secret isolation and deployment-wide quotas in addition to local controls. Strategy proposals must continue to produce only the supported schema and pass graph validation. Real-time exchange data, paper execution, private exchange accounts and real orders remain separate unimplemented capabilities.

Refer to [SECURITY.md](SECURITY.md) and the project's feature-status/data-provider documentation for the actual trust boundaries and research assumptions.
