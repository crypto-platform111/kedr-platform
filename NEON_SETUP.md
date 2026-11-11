# Neon PostgreSQL setup

This application keeps its Python/FastAPI backend, psycopg driver, application
accounts, and Vercel Queues worker. Neon supplies PostgreSQL only. `neon deploy`
applies database-service policy; it does not deploy the Vite website or Python API.

## Initialize and deploy

Run from the repository root with Python 3.13, Node.js 24 and Git installed:

```powershell
npm i -g neon@latest
neon login
neon init -y --org-id org-wild-meadow-24658081 --project-id rapid-snow-49615570 --branch production --services postgres
neon deploy
```

Keep the existing `neon.ts` policy when repeating setup. The linked `.neon` file
and downloaded `.env.local` (or an existing `.env`) stay ignored. Never paste a
database URL or CLI token into Git or a `VITE_*` variable. CLI OAuth sign-in and
MCP OAuth sign-in are separate; no API key is required in project MCP configuration.

## Application wiring

`scripts/neon-environment.mjs` reads the selected Neon env file and supplies these
values only to the server processes it starts:

| Neon variable | Application use |
| --- | --- |
| `DATABASE_URL` | Pooled TLS URL mapped to `KEDR_DATABASE_URL` for API and worker traffic |
| `DATABASE_URL_UNPOOLED` | Direct TLS URL used by the explicit migration command |
| `NEON_BRANCH` | Branch label displayed during startup |
| `NEON_BRANCH_ID` | Retained branch metadata; not a browser credential |
| `NEON_FUNCTION_HOST_SUFFIX` | Retained CLI metadata; no Neon Function is enabled |

The launcher requires both database URLs and TLS. It selects durable jobs,
disables external AI and historical adapters, and uses a separate scratch
directory. It does not copy or import local SQLite records. The ordinary Windows
launcher and SQLite defaults remain available.

On Windows, the psycopg adapter resolves a fresh IPv4 address for Neon endpoints
to avoid long retries on networks with unusable IPv6 routes. It retains the
original hostname and TLS/channel-binding parameters, honors an explicit
`hostaddr`, and leaves Linux and other PostgreSQL hosts unchanged.

```powershell
npm ci --ignore-scripts
npm --prefix frontend ci --ignore-scripts
npm run build
npm run db:migrate:neon
npm run dev:neon
```

Open `http://127.0.0.1:3000`. `/api/health` must report `storage: postgresql`,
`job_mode: durable`, and `execution_enabled: false`. Create a demo workspace and
use the labelled synthetic datasets. Stop the development server with Ctrl+C.
The launcher uses the existing portable Vercel CLI when present, or obtains the
pinned CLI through npx. An explicit `KEDR_VERCEL_CLI_PATH` can select an installed
CLI entrypoint. `KEDR_NEON_ENV_FILE` selects a separate development/test env file;
otherwise an existing `.env` takes precedence over `.env.local`, matching Neon CLI.

Test migrations and workflows on a separate branch before applying them to
production. Use direct connections for migrations and pooled connections for app
traffic. Never point an unrelated preview at production data.

For browser integration tests against a distant cloud database, set
`KEDR_E2E_NETWORK_TIMEOUT_MS=45000`. This adjusts browser wait budgets while
retaining the same workflow assertions; the usual local default remains 15
seconds. Co-locate the hosted API and database to avoid cross-region SQL latency.

## Skills and MCP

The project has the seven Neon skills under `.agents/skills`; the Neon CLI can
check them with `neon skills status`. Local agent configuration and skill bundles
are excluded from application uploads. The user-level Neon plugin is retained.
The project `.codex/config.toml` adds an OAuth-only MCP endpoint pinned to this
Neon project. Reopen this project in Codex to load new project MCP configuration;
complete the separate MCP sign-in if prompted. No token is stored in that file.

## Vercel cloud hosting

Use the existing Services configuration described in `VERCEL_DEPLOYMENT.md`.
Configure the production pooled URL as backend-only `KEDR_DATABASE_URL` (or use
the supported cloud `DATABASE_URL` fallback), secure cookies and `CRON_SECRET` in
Vercel. The local launcher sets insecure cookies only for loopback HTTP; do not
copy that local setting into cloud HTTPS hosting. Verify deployed queue-worker
duration and the full cloud workflow separately.

## Windows command wrapper

If PowerShell blocks `npm.ps1` under its execution policy, use `npm.cmd` for
these commands (for example, `npm.cmd run dev:neon`). No execution-policy change
is required. The same applies to `neon.cmd` if its PowerShell wrapper is blocked.
