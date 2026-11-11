# Neon setup completion — 2026-11-11

KEDR is linked to org-wild-meadow-24658081 / rapid-snow-49615570, production.
Neon CLI 9.2.0 was installed globally. The requested init and deploy succeeded;
PostgreSQL was reused and its service policy applied. Six application migrations
were applied to production, which was empty beforehand. No personal SQLite data
was imported. The app is running locally at http://127.0.0.1:3000 using Neon.
This is not a public Vercel deployment. No Git commit or push was performed.

## Changes

- Fetched the requested official Neon SKILL.md to ignored verification storage.
- Retained seven existing project Neon skills. Current CLI status: five current;
  neon-auth and neon-functions have upstream updates available. Neither is used
  by this PostgreSQL integration, and their existing files were preserved.
- Neon init installed user-level Codex/VSCode plugin integration and Copilot CLI
  skills/MCP configuration. Existing configuration was retained.
- Added project .codex/config.toml OAuth MCP endpoint pinned to this project.
  Reopen D:\CryptoPlatform in Codex and authorize MCP if prompted. CLI login is
  working; an authenticated MCP tool call has not been verified in this session.
- Created neon.ts policy, ignored .neon project link, and ignored .env.local with
  CLI-managed database credentials. No existing env file was overwritten.
- Added root package.json/lockfile, @neon/config and @neon/env, build, migration,
  and development commands.
- Added scripts/neon-environment.mjs, neon-migrate.mjs and neon-dev.mjs for
  server-only pooled connections, direct migrations and both Vercel services.
- Updated backend/app/postgres.py for fresh IPv4 resolution on Windows Neon
  connections and safe read/write handling; retained TLS hostname validation
  and write savepoints. Combined database setup statements in backend/app/db.py
  to reduce remote round trips while retaining timeouts and transaction locking.
- Added three connection tests and three launcher tests. Added an explicit cloud
  browser timeout override, preserving ordinary local defaults.
- Added NEON_SETUP.md, README link, and additive Git/Vercel exclusions for local
  Neon links, skills and agent configuration.

## Verification

- npm run build: passed, built in 39.11s; existing bundler warnings remain.
- Backend: 145 passed, 21 skipped (opt-in PostgreSQL and optional history tests).
- Launcher: 3 passed; focused backend hosting/connection/durable checks: 40 passed.
- Browser-to-API-to-Neon-to-queue workflow: 6 passed, 2 optional-history skipped,
  zero unexpected/flaky cases. Run completed 2026-11-07 on an isolated schema-only
  verification branch. Its synthetic results included four successful backtests,
  four research jobs and three saved ML artifacts across verification attempts.
- Temporary verification branch expired automatically; refreshed branch listing
  on 2026-11-11 contains production only.
- Fresh production check: 26 public tables, six migrations, pooled TLS required.
- Fresh app health: status ok, storage postgresql, job_mode durable,
  execution_enabled false. Frontend HTTP 200.
- Temporary-table probe: 15s lock timeout, 30s statement timeout, advisory lock
  and integrity-error recovery all passed; no permanent probe table retained.
- Built frontend: 52 files checked, zero server credential matches.

Initial verification found Windows IPv6 connection delays and overly short
15-second UI waits across regions. Transport handling and explicit 45-second
cloud test waits resolved those failures. PowerShell blocked npm.ps1; npm.cmd
worked without changing machine policy. No research reservations, collectors,
trading accounts or production trading systems were touched.

For startup and remaining Vercel cloud environment configuration, see
NEON_SETUP.md. Local changes have not been published to GitHub.
