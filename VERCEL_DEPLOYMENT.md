# KEDR on Vercel Services

The user confirmed the service names, public paths and absence of internal service bindings, and selected a durable hosted platform. The implementation now supports shared PostgreSQL storage and Vercel Queues. No personal SQLite database or research data is migrated or uploaded. The Windows installation keeps SQLite and its existing local worker defaults.

## Confirmed service layout

| Service | Root / entrypoint | Public paths | Bindings |
| --- | --- | --- | --- |
| `app` | `.` / `pyproject.toml` selecting `backend.app.main:app`, Python 3.13, FastAPI | `/api` and `/api/*` | None |
| `frontend` | `frontend`, Vite static `dist` | All remaining paths | None |

Top-level rewrites route the API first and the frontend last, preserving `/api`. The frontend-only SPA rewrite lists the actual React route prefixes and supports direct links such as `/market` and `/builder/<id>`; `/` serves the index directly. JavaScript, CSS and Vite development modules bypass it instead of receiving HTML. Add any new React route prefix to this rule. This avoids conditional `has` rewrites, which Vercel does not evaluate in local development. Built assets remain static files. Unknown API routes return JSON errors, not SPA HTML.

The browser already requests relative `/api` URLs with same-origin cookies and CSRF headers. A static Vite build has no runtime function that calls another repository service. Its localhost proxy is development-only. Therefore no service binding is required or invented. Any future server-side caller must declare a binding on the caller, use the injected URL at function runtime, and keep it out of `VITE_*`, builds and middleware. Do not manually set generated binding variables.

No service is internal-only in this confirmed layout. FastAPI's existing `/docs`, `/redoc` and `/openapi.json` are not publicly routed on Vercel. The queue subscriber is a private generated function within the Python service, not a third public service or an unauthenticated HTTP callback.

## Cloud resource setup

The connected Vercel account was observed on Hobby during preparation. The repository is now public, and the user explicitly confirmed keeping it public and pushing these changes. Vercel's private-organization repository restriction therefore does not block this import. If the repository is made private later, Git deployment from the organization requires an eligible Pro team. No plan upgrade, paid trial or visibility change is performed by this configuration.

1. Import the repository into the selected Vercel team. Keep the project root at the repository root (`.`), not `frontend`. Select the **Services** framework preset, use the checked-in `vercel.json` and select Node 24 LTS. Services is a Vercel Beta feature.
2. Attach a **new, dedicated PostgreSQL database**, preferably Neon through Vercel Marketplace, in a region matching the functions. Do not attach any trading/research database. No existing local records need to be copied.
3. Configure `KEDR_DATABASE_URL` as a backend-only PostgreSQL URL requiring TLS. In Vercel cloud only, the application also accepts Marketplace-injected `DATABASE_URL`; explicit `KEDR_DATABASE_URL` takes precedence. Use separate preview/development and production databases or branches. Never point previews at production state. A generic local-shell `DATABASE_URL` is deliberately ignored.
4. Set `KEDR_SECURE_COOKIES=1`. Generate a random **at least 32-character** `CRON_SECRET` directly through your secure configuration workflow. Leave `KEDR_LEGACY_ROOT` blank and `KEDR_AI_PROVIDER=disabled` unless separately configuring those optional sources. Do not paste credentials into chat, source files, frontend variables or clone URLs.
5. PostgreSQL selects `durable` jobs automatically. `KEDR_JOB_MODE=local` exists for local SQL integration testing only and is rejected in Vercel cloud. Cloud startup without shared storage fails with a clear configuration error instead of creating disposable accounts in `/tmp`.
6. Deploy after environment/resource configuration. The service entrypoint must remain `pyproject.toml`: `[tool.vercel]` selects the FastAPI module and `[[tool.vercel.subscribers]]` discovers `backend.app.queue_bridge`. Pointing the service directly at the API module skips subscriber generation in the current builder. Vercel Queues uses its platform authentication. No manually configured internal service URL is needed. Topic: `kedr-research-work`; consumer group: `kedr-work-v1`.

The adapter automatically applies six additive migrations under a database advisory lock, including immutable-version/result triggers and a shared authentication-attempt ledger. Application credentials need permission to create the schema, indexes and trigger functions for a new database. Later production operations should separate migration and runtime roles if required by the operator's security policy.

Use pooled/serverless-compatible PostgreSQL connections and retain TLS. Connection failures and constraint errors are sanitized; database URLs are never returned by health/status endpoints. Host/origin allowlists use exact Vercel-generated hostnames. A custom domain additionally needs its exact `KEDR_ALLOWED_HOSTS` and HTTPS `KEDR_ALLOWED_ORIGINS` values; no wildcard Vercel origin is automatically trusted.

## Durable execution and recovery

A hosted submission commits the existing immutable job reference and its outbox record in one PostgreSQL transaction. The request tries a bounded queue publish before returning. If publishing fails, the job remains queued and recoverable; it is not falsely marked completed or silently discarded. Queue payloads contain only a random work reference, not user records, datasets, credentials or models.

The subscriber awaits computation and its fenced database commit before acknowledging. An awaited worker thread permits SDK lease renewal; no job is detached after the response. Cross-instance leases, fixed attempt limits and deterministic saved IDs prevent duplicate deliveries or expired workers from registering duplicate runs/models. Cancellation suppresses artifact publication; a cancellation from another API instance cannot promise to kill that worker's already-running process immediately. ML processes retain their existing bounds.

Hosted startup never marks another instance's running jobs failed. Short PostgreSQL transactions use a global advisory lock to preserve existing version, budget and admission checks across instances. Computation and network calls stay outside it. This is a correctness-first throughput trade-off, not a large-scale performance claim. Shared admission remains four backtests and two research jobs, including one unfinished research job per owner. Authentication-attempt budgets are shared across instances.

`GET /api/internal/dispatch` requires `Authorization: Bearer <CRON_SECRET>` and is excluded from the API schema. An absent/short secret is rejected; a bad token cannot dispatch work. The checked-in daily cron is plan-compatible without silently selecting a paid higher-frequency schedule. Authenticated owner job polling also attempts bounded outbox dispatch after ownership verification, so active clients can recover failed initial publishing promptly.

The application lease is ten minutes and stale pending-delivery eligibility fifteen minutes. These are **not guaranteed recovery times**: with the browser closed, a failed/unpublished/lost queue message can wait until the daily cron, approximately 24 hours plus scheduling jitter. An operator who needs a shorter recovery SLO should configure an eligible faster protected schedule and verify its cost/plan. At-least-once queue delivery is handled through idempotency and fencing, not described as exactly-once message delivery.

Publication replay remains synchronous within its HTTP request and creates a publication only after exact result equality; it is not falsely labelled an asynchronous durable operation. All new results/artifacts are stored in PostgreSQL. Large hosted JSON responses use chunked streaming while keeping the browser's existing JSON contract; existing arrays are not truncated. Research retains its existing 3 MB artifact bound.

The API has an explicit 300-second function budget. The current Python builder generates subscriber functions using the project/platform duration default rather than the API's file-specific rule. Verify the generated worker's deployed duration before accepting work; target 300 seconds, with room for the existing 60-second ML wall budget and persistence overhead. Do not assume an API duration setting also configures its queue worker.

## Local development and verification

Install the pinned Python/frontend dependencies with `scripts/setup.ps1`. For ordinary Windows use, `scripts/start.ps1` remains unchanged. For all services together, use a disposable local directory and a current Services-capable Vercel CLI:

```powershell
$env:KEDR_DATA_DIR = Join-Path $env:TEMP ('kedr-vercel-check-' + [guid]::NewGuid())
$env:KEDR_LEGACY_ROOT = ''
$env:KEDR_AI_PROVIDER = 'disabled'
$env:KEDR_ALLOWED_ORIGINS = 'http://127.0.0.1:3000,http://localhost:3000'
vercel dev --local --listen 127.0.0.1:3000
```

Local-only mode does not link a cloud project or pull secrets. SQLite/local workers can verify route/UI behavior, but cannot prove cloud persistence. To test shared storage, use a **dedicated test database** with `KEDR_TEST_POSTGRES_URL` when running pytest. The tests create disposable random schemas and never use the personal hosted URL. They do not copy the user's installed database. Local verification also exercised the full browser/API/PostgreSQL flow through Vercel CLI 65.8.0's actual Queues emulator and generated private Python subscriber, completing synthetic backtest, scenario and ML jobs. This is local integration evidence; cloud deployment remains a separate acceptance check. Transport-failure tests deliberately isolate the external queue service.

Before accepting hosted traffic, verify `/api/health` reports `postgresql` / `durable`, API 404s are JSON, deep links and JS/CSS load, login/CSRF and owner isolation hold, and a queued synthetic backtest/ML task completes through the real subscriber and survives new API instances. Test dispatch authorization, duplicate deliveries, stale leases and a new deployment. Keep a backup/restore and retention policy for the new platform database. No cloud success is inferred merely from a local listener.

Historical archives are not bundled and are explicitly unavailable without an independently installed verified inventory. Six labelled synthetic datasets remain the engineering fallback. This work does not enable exchange accounts, collectors or live trading.

## References

- [Services, routing and runtime bindings](https://vercel.com/docs/services)
- [Python Queues SDK](https://vercel.com/docs/queues/python-sdk)
- [FastAPI runtime](https://vercel.com/docs/frameworks/backend/fastapi)
- [Git integration plan restrictions](https://vercel.com/docs/git)
- [Large function responses and streaming](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions)
