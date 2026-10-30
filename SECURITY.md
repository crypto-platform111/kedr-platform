# KEDR 0.2 security and isolation

Local operation defaults to API 127.0.0.1:8710 and frontend 127.0.0.1:5173. Do not expose the development servers publicly. An implemented Vercel Services mode uses shared PostgreSQL and durable Queues; follow [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) for provisioning and required hosted verification. This release has no private exchange-account or order-routing integration.

## Identity and requests

Passwords use salted scrypt; random session tokens are stored as hashes, with seven-day expiry and HttpOnly/SameSite Strict cookies. Protected mutations require CSRF. Demo creates a separate identity, not a shared password; lost demo cookies do not provide a recovery flow. Email verification/recovery/MFA remain absent.

Owner checks cover private strategies/versions/jobs/runs, conversations/proposals, chart preferences, research/model records and audit data. Public community only exposes explicitly published snapshots. Knowing another private ID does not grant access.

Trusted hosts default to loopback/testserver, with exact generated deployment hosts added in Vercel mode. Explicit origins and credentialed CORS are restricted to configured exact origins and the request origin; no wildcard Vercel origin is automatically trusted. KEDR_ALLOWED_HOSTS is an optional explicit extension, not permission to bind development servers publicly. Local HTTP uses KEDR_SECURE_COOKIES=0; hosted TLS requires secure cookies and separately verified proxy/origin/custom-domain configuration.

Actual streamed mutation bodies cap at 200,000 bytes. Strategies cap at 150,000 serialized characters, 80 nodes and 150 edges. Typed graphs reject cycles/incompatible inputs/unsupported parameters and never evaluate Python/JavaScript/shell/SQL or generated expressions. Responses use no-store/nosniff/same-origin referrer policy; a deployment CSP/TLS/HSTS design remains work.

## Immutable research and migration

Versions/results/publications are protected by SQLite triggers locally and corresponding PostgreSQL triggers in hosted mode. A draft deletion archives it. Publication requires an owned successful run, exact version/config/source and complete replay equality. The badge verifies software output, not alpha. Database triggers are not tamper-proof against privileged database writers.

Migration 004 is additive. Proposal payloads and native model artifacts are immutable; approval/rollback create versions with optimistic draft-hash checks. Backup/restore details are in V02_MIGRATION.md. The pre-upgrade source/database snapshot contains private data and must remain local.

Additive migrations 005/006 support the hosted outbox and shared authentication throttling. PostgreSQL migrations serialize under an advisory lock. No personal SQLite database is uploaded or automatically migrated; previews must use separate state from production. Use TLS and scoped database credentials, and verify hosted backup/restore and retention separately.

## Bounded computation

Local backtests: one in-process thread/four admitted tasks; v1 20,000 bars, v2 50,000. Local replay waits 60 seconds but cannot forcibly terminate its thread. V2 traces cap at 3,000 decisions/6,000 order events/20,000 account states with explicit dropped counts.

Local research: one worker/two admitted jobs, at most one active per owner and 100 stored records per owner. Scenarios are bounded thread replays. ML alone runs a fixed separate child with 256 MiB/30 CPU seconds/60 wall seconds, bounded I/O and cancellation. Windows enforcement fails closed. Child environment excludes parent API/session secrets. This is trusted fixed code, not a hostile-code or OS network sandbox. SQLite/local-worker mode requires a single API process.

Hosted mode uses a transactional outbox, private authenticated Vercel Queues subscriber, shared admission, bounded retries and lease-fenced commits. The subscriber awaits computation and persistence before acknowledgement. The protected dispatcher requires a server-only CRON_SECRET; owner polling and the configured daily cron provide recovery, without a short recovery-time guarantee. Cross-instance cancellation suppresses result publication but cannot promise immediate termination of an already-running child. These mechanisms do not replace general computation isolation, storage quotas or retention policies.

Chart requests cap at 5,000 candles/eight indicators. Authentication bootstrap throttling is in-memory locally and shared through PostgreSQL in hosted mode. Total users/strategies/backtests/audit storage still need an operational quota/retention policy.

## AI consent, secrets and spending

The real Responses adapter defaults disconnected. Backend-only key/model/provider and positive conservative pricing ceilings are required before external requests become available. Per-message consent is mandatory; opening the drawer does not call a provider. External proposals do not edit automatically.

Structured response/schema, graph validation, measured-evidence references, response/context caps, owner/global concurrency, timeout and conservative daily request/token/USD reservations are enforced. Ambiguous failures retain accounting; transport timeout is not retried. These are local controls, not a provider invoice or guarantee of qualitative model correctness. See AI_INTEGRATION.md.

Never put secrets in VITE_ variables or reuse the legacy environment. Do not print keys or commit .env. ML children receive no provider keys. Local SQLite/conversations/results/backups are not encrypted at rest. Protect data/, backups/ and logs with Windows permissions. Configure and verify hosted provider encryption, access control and backup policy separately. External consent sends bounded private context to the configured provider; store=false is not a replacement for reviewing provider data policy.

## Protected source boundary

Adapters read only fixed allow-listed existing pre-2026 Spot archives and their manifests, validate containment/SHA256/CRC/schema/clocks and write no legacy source. The new minute example is January 2025 only. No protected reservation, live market DB, collector, private account or order is accessed. Missing history never falls back to synthetic prices. Advanced provider contracts do not connect a feed.

News remains labelled fixtures. Live/paper execution is disabled. Public feed collection, notifications, paid services and account access require separate implementation/authorization.

## Operations before any public release

Required: verified hosted TLS/service identities, hardened identity and recovery, secret management, encrypted/tested backups, operational queue recovery tests, hard process isolation for general computation, per-user/storage/CPU quotas, pagination/retention, monitoring/incident handling, security review and provider licensing/privacy controls. Hosted persistence/queue code is implemented; resource provisioning and successful production verification remain separate requirements.

Use SQLite backup API or stop this platform before copying a database; copying an active main file can miss WAL commits. Restore into a separate directory and preserve the upgraded database. Verification logs under verification/v02/ show executed checks; passing local tests is not penetration testing or security certification.
