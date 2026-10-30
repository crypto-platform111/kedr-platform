# KEDR 0.2 — local trading research studio

KEDR is a Russian-first, English-capable strategy research application. Version 0.2 adds blank-canvas creation, a broader typed strategy language, historical candlestick charts, engine decision traces, bounded comparisons and a real local ML example. External AI has an implemented consent-gated adapter and remains disconnected until configured.

The application runs locally without exchange credentials, paid services or new market downloads. Historical simulations and chronological ML tests remain retrospective research, not independently validated forecasts or verified executable returns.

## Windows setup for a fresh clone

Install Git for Windows, **Python 3.13** with the Windows `py` launcher, and **Node.js 24 LTS** with npm. Open a new PowerShell window and check `py -3.13 --version`, `node --version` and `npm.cmd --version`. Microsoft Edge is needed only for optional browser tests. The organization administrator must grant your GitHub account access to this private repository before cloning.

~~~powershell
git clone https://github.com/crypto-platform111/kedr-platform.git
Set-Location .\kedr-platform
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
~~~

The setup script locates the repository from its own path, creates `.venv`, installs locked dependencies, copies `.env.example` only when `.env` is absent and applies database migrations. Existing configuration and database records are preserved. No personal drive mapping, historical archive, API key, trading account or paid service is required for demo mode. Authenticate to GitHub using Git Credential Manager or the GitHub CLI browser workflow; do not embed access tokens in clone URLs.

A clean clone has seeded, clearly labelled **synthetic demo** BTC/ETH/SOL 4h datasets and their strict daily aggregates. It creates a new empty local database, with no existing users or saved runs. Historical adapters remain unavailable until separately installed archives satisfy their manifest and checksum requirements. They never substitute synthetic candles for requested historical data.

Equivalent manual setup from the repository root:

~~~powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.lock.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
Push-Location frontend
npm.cmd ci --ignore-scripts
Pop-Location
.\.venv\Scripts\python.exe -c "from backend.app.db import Database; Database('data').initialize()"
~~~

The API also applies numbered SQL migrations automatically at startup. Default storage is `data/platform.sqlite3`. Local accounts, sessions and workspaces stay in that ignored database.

## Start and stop

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
~~~

Open **http://127.0.0.1:5173/**. API health: **http://127.0.0.1:8710/api/health**; interactive API documentation: **http://127.0.0.1:8710/docs**. Register locally or create a demo workspace, choose a synthetic dataset, and use its advertised dates. Demo authentication and demo market prices are separate concepts. The launcher binds to loopback, checks both endpoints, starts hidden owned processes and refuses occupied ports. Logs and process records are in ignored `data/runtime/`. Checkout paths may contain spaces and need no particular drive letter.

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
~~~

The stop script verifies process identity and targets this platform only. It does not stop the microstructure collector or another application. The -Production option serves local Vite preview, not an internet production deployment.

`start.ps1 -ValidateOnly` checks runtime readiness without starting a process. `stop.ps1 -ValidateOnly` verifies the recorded processes without stopping them. For separate development terminals, run these commands from the repository root:

~~~powershell
# Terminal 1: backend; migrations apply automatically.
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8710 --no-access-log

# Terminal 2: frontend.
Set-Location frontend
npm.cmd run dev
~~~

The launch script loads this checkout's `.env`; direct `uvicorn` uses process environment and application defaults. Set any desired `KEDR_*` values in that terminal before starting it. The optional ignored `data/local-settings.json` preserves source configuration for an existing installation; it is not needed or distributed in a clean clone.

## Connected workflows

1. Register or create an isolated demo workspace. Demo authentication does not determine whether prices are synthetic or historical.
2. Open New strategy and choose a truly blank schema-2 canvas, guided rule builder, or original template. Templates retain schema 1 for reproducibility.
3. Connect typed market, indicator, condition, action and risk nodes. Guided rules create the same visible JSON graph; plain-language summaries describe its wiring. Save incomplete drafts, undo/redo and create immutable versions. Execution requires a complete valid graph.
4. Choose matching data/dates, costs and an explicit execution clock. Simulation is single-asset long/cash.
5. Inspect saved analytics and the historical terminal. New schema-2 runs retain engine decisions, orders and account/risk states. Select a chart event or timeline row to inspect recorded conditions. Old runs without traces remain explicitly without traces.
6. Use fixed cost or chronological diagnostics and saved-run comparison. No automated parameter search is performed.
7. Open ML Studio for bounded logistic-direction or ridge-return training. Inspect baseline, purged chronological splits, metrics and native artifact. Training does not automatically activate prediction nodes.
8. Use the copilot for deterministic local explanations, or configure external AI and consent to each outbound message. AI proposals require diff review/approval; approval and rollback create new versions and reject stale conflicts.
9. Reopen work from the dashboard. Local community publication requires exact replay equality. A reproducibility badge does not validate alpha or publish the website online.

## Data and execution

| Source | Scope |
| --- | --- |
| Original verified history | BTC/ETH/SOL Spot 4h, 2022–2025; original IDs, bars, metadata and hash semantics preserved |
| New intraday examples | BTC Spot January 2025 genuine 1m; strict 5m/15m/1h aggregation |
| New daily datasets | Complete six-bar UTC groups of existing BTC/ETH/SOL 4h candles |
| Synthetic demonstrations | Separate labelled 4h and aggregated 1d examples; no historical fallback |

Adapters verify source SHA256/ZIP/schema/UTC/OHLCV. They read no 2026 market observations or live research database. Historical receipt timing is unknown; candle availability is an explicit assumption. Missing intervals are not interpolated. True VWAP requires actual quote/base volume.

Schema 1 retains kedr-candle-1.0.0 and minimum open **i+2** execution. Schema 2 defaults to full-bar embargo, also minimum i+2. Its next-bar-open optimistic mode uses i+1 and zero assumed delay; it is explicitly optimistic. Higher-timeframe inputs use only candles completed and available at the decision clock.

Microstructure, funding/basis/OI/liquidation, news/sentiment and ML prediction nodes remain provider-required. General state flags are preview-only. Shorts, leverage and portfolio execution are unsupported. News is a labelled fixture. Bots remain execution-disabled. No live feed, paper daemon, private account, billing or order router is connected.

## Configuration and migration

Use this project's `.env.example`; never copy another installation's environment or credentials. Keys stay backend-only, never in `VITE_` variables. `KEDR_DATA_DIR` defaults to `data/`. Leave `KEDR_LEGACY_ROOT` blank for demo-only use; optional history needs an authorized external checkout with the exact manifests described in [DATA_PROVIDERS.md](DATA_PROVIDERS.md). An arbitrary folder of CSVs does not meet that contract. Setup does not download market data. Local HTTP uses `KEDR_SECURE_COOKIES=0`.

Additive migrations preserve existing users, versions, runs and publications. The OpenAI adapter defaults to not_connected; model/key/provider, operator-entered conservative price ceilings and explicit request consent are all required. No paid call is made by setup, demo mode or the normal test suite. Never copy private databases, sessions, real `.env` files or historical archives into source control.

## Setup and checks

Dependencies are pinned in `requirements.lock.txt` and `frontend/package-lock.json`. A normal clone uses Node on PATH; an existing ignored `tools/node-path.txt` is an optional portable-runtime fallback. Run these checks from the repository root:

~~~powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend
Push-Location frontend
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
Pop-Location
~~~

Backend tests use isolated local storage. Integration cases requiring optional historical archives skip when that source is not configured; a configured but corrupt source must fail rather than fall back. Demo functionality remains tested without the original research checkout.

Start the local servers before browser E2E:

~~~powershell
Push-Location frontend
npm.cmd run test:e2e
Pop-Location
~~~

Browser checks use installed Microsoft Edge without downloading browser payloads. They create local demonstration records; use a disposable test installation if you want an empty database afterward. No test connects a private exchange or places orders. Test outputs, runtime logs, dependencies, build outputs, database files and private data are ignored.

See [FEATURE_STATUS.md](FEATURE_STATUS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_PROVIDERS.md](DATA_PROVIDERS.md), [AI_INTEGRATION.md](AI_INTEGRATION.md), [ML_INTEGRATION.md](ML_INTEGRATION.md), [SECURITY.md](SECURITY.md) and [ROADMAP.md](ROADMAP.md). Frozen research, reservations and the collector remain outside the write boundary.
