# KEDR 0.2 architecture

KEDR defaults to a local Vite/React/TypeScript SPA at 127.0.0.1:5173, with a FastAPI API at 127.0.0.1:8710 and SQLite platform storage. An implemented hosted mode uses Vercel Services, shared PostgreSQL and Vercel Queues; configuration, provisioning and verification requirements are in [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md). Existing research is outside the write boundary. No legacy runner or collector is imported.

## Components and data flow

~~~text
Browser / same-origin API proxy / owner session + CSRF
  -> FastAPI validation, ownership and immutable snapshots
     -> schema-version dispatcher -> frozen v1 or new v2 engine
     -> explicit local data adapter -> read-only verified archives
     -> local worker or hosted durable queue -> immutable result + actual v2 traces
     -> local/hosted research queue -> fixed scenarios or supervised ML subprocess
     -> copilot -> deterministic offline explanation
                   or consent + budget -> OpenAI Responses -> validated proposal
     -> SQLite (local) or PostgreSQL (hosted) / audit / chart preferences / native model registry
~~~

XYFlow is the typed graph editor. ECharts is retained behind the FinancialChart component for candles, volume, overlays, an oscillator pane, crosshair, zoom and event markers. A separate market endpoint supplies genuine local bars and the same backend indicator implementation as the strategy engine. Chart rendering does not contact a market-data vendor.

The frontend provides landing/auth/onboarding, dashboard, creation/builder, market terminal, saved results/analyst, research comparison, ML, intelligence fixtures, community, disabled bots, integrations and settings. Shared context owns user, locale/theme/timezone. The guided builder and copilot proposals use the same schema-2 graph as the visual editor.

## Backend files

| File | Responsibility |
| --- | --- |
| main.py | Auth/resource APIs, bounded backtest queue, immutable versions/results and replay publications |
| auth.py / db.py | Password/session/CSRF, transactions, canonical finite JSON, migrations and audit |
| hosting.py / postgres.py | Exact hosted origin/host configuration and opt-in shared PostgreSQL compatibility adapter |
| durable_jobs.py / queue_bridge.py | Transactional outbox, cross-instance claims/fencing and private Vercel Queues subscriber |
| domain.py / engine.py | Schema-version dispatch |
| domain_v1.py / engine_v1.py | Frozen original definitions and semantics |
| domain_v2.py | Typed catalog/statuses, blank graph, parameter/DAG/risk validation |
| engine_v2.py | Causal indicators, as-of auxiliary sources, explicit clocks, long/cash/risk/accounting and actual traces |
| data.py / data_v2.py | Preserved original datasets plus bounded intraday/strict coarsening |
| market.py | Authenticated bounded chart/capability endpoints and shared indicator series |
| market_providers.py | Permission, timestamp meaning, availability, source version/quality and future provider protocols |
| copilot.py | Owner conversations, actual consent-gated Responses adapter, budgets/evidence/proposals/approval/rollback |
| research.py | Owner research jobs, fixed scenarios/comparison/preferences and descriptive week uncertainty |
| process_runner.py / ml_worker.py | Fixed supervised subprocess and small real native logistic/ridge experiment |
| providers.py / contracts.py | Provider status, fixtures and disabled execution boundary |

## Compatibility and persistence

The schema field chooses the engine; old immutable versions are never reinterpreted as schema 2. Public ENGINE_VERSION remains the legacy constant for compatibility; run provenance records the actual engine. Original six data IDs retain exact bars/metadata/provenance/hash semantics. New IDs and assembly rules are separate.

Migrations 001–003 remain unchanged. Additive 004_research_studio.sql creates copilot_conversations/messages/proposals, ai_usage, chart_preferences, research_jobs and model_registry. Original users/sessions/strategies/versions/jobs/backtests/publications/audit/ML drafts remain. Older extension tables remain extension contracts; active 0.2 ML uses research_jobs and model_registry. Proposal payloads and registry artifacts are immutable by trigger. Approval/rollback change the draft and create another immutable version, not a historical edit.

Private resources are owner-checked. Versions/results/publications retain immutable provenance; deletion archives a draft. Publication reruns the exact version/data/config and requires equality of the full result. Reproducibility proves software replay, not independent economic validation.

Additive migrations 005/006 provide durable work/outbox metadata and the shared authentication-attempt ledger. Hosted PostgreSQL has corresponding explicit migrations and immutable-record triggers; no personal SQLite records are automatically copied. Short hosted transactions serialize existing admission/version/budget checks through a database advisory lock. This preserves correctness across instances but limits throughput.

## Resource boundaries

Local backtests use one thread worker and four admitted tasks. A local publication waits at most 60 seconds; its bounded thread may finish after the wait. Original v1 caps 20,000 bars; v2 caps 50,000 source bars. V2 trace storage is capped independently: 3,000 decisions, 6,000 order events and 20,000 account states. Dropped counts/truncation are explicit; metrics still use the complete admitted run.

Local research has one worker/two admitted tasks, at most one pending/running task per owner and 100 records per owner. Scenarios are fixed engine replays in this thread. ML has a separate fixed Python process, 20,000-candle/16 MB input ceiling, 256 MiB/30 CPU seconds/60 wall seconds and 2 MB child output; saved research results cap at 3 MB. Windows Job limits fail closed when unavailable. Local workers are not a durable distributed scheduler or arbitrary-code sandbox.

Hosted mode replaces post-response local workers with a transactional PostgreSQL outbox and an awaited private Vercel Queues subscriber. Shared admission retains four backtests/two research jobs and the per-owner research limits. Cross-instance leases, bounded retries and fenced commits suppress duplicate or cancelled result publication. Publication replay remains synchronous. Recovery scheduling and cancellation limitations are explicit in [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md); this is not a general hostile-code sandbox or a guarantee of production availability.

Chart requests cap at 5,000 actual bars/eight indicator series. Backend computes warm-up on prior native history, then returns the requested bounded window without random candle sampling. Missing windows/indicators remain explicit.

## Clocks, providers and safety

V1 i+2 semantics remain. V2 full-bar embargo is default; next-open mode explicitly assumes zero latency and is labelled optimistic. Higher-source candles are aligned by completion/availability, never by their opening timestamp alone. Strict resampling needs every native source bucket; no smaller interval is invented.

Provider contracts separate event, period end, receipt, first seen and availability clocks. Archive retrieval/version clocks do not prove original receipt. Liquidations require an exchange label; settled and indicative funding are distinct families. The contracts do not themselves connect advanced sources or make those nodes executable.

External AI is optional and server-only. Its structured graph passes the same executable validator. Numeric claims must match supplied saved evidence. Consent authorizes the outbound message, not editing; edit approval remains separate. Default mode is deterministic local explanation. ML artifacts have no executable strategy-node adapter.

No private account, order router, live recorder, paid service or protected reservation is activated. Public deployment still needs the hardening listed in SECURITY.md and ROADMAP.md. See V02_MIGRATION.md and verification/v02/ for upgrade preservation and executed evidence.
