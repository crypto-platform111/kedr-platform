# KEDR 0.2 feature status

Implemented means a real local flow, not independently validated skill, verified fills or public deployment.

| Area | Status | Actual behavior / boundary |
| --- | --- | --- |
| Identity/preferences | Implemented locally | Registration/login/logout, scrypt, cookie sessions, CSRF, owner checks, onboarding, RU/EN, dark/light and timezone. No recovery/email/MFA. |
| Dashboard | Implemented | Own strategies/versions/runs and actual activity; no invented live balances. |
| Blank canvas | Implemented | Empty schema-2 graph. Incomplete drafts save, incomplete graphs cannot run. |
| Visual editor | Implemented | Typed ports, categorized library, forms, validation, pan/zoom/fullscreen, undo/redo, draft autosave and immutable versions. |
| Guided rules | Implemented subset | SMA/EMA/WMA crossover or above/below trend, optional RSI, long/cash, allocation/stop/target. Same JSON graph; no universal language parser. |
| Plain-language rules | Implemented | Summaries derived from visible graph wiring. |
| Original templates | Preserved | Five schema-1 examples, original four-hour semantics. 200 bars do not mean 200 days. |
| Indicators | Implemented | Existing SMA/EMA/RSI/MACD/Bollinger/returns/volatility plus WMA/momentum/log returns/extrema/z-score/percentile, ATR/ADX/stochastic/Donchian, quote/base VWAP, OBV/MFI, correlation/relative price/difference and trade count with required fields. |
| Boolean/temporal logic | Implemented | Comparisons/crossings/equality/tolerance, AND/OR/NOT, consecutive/rolling confirmation, cooldown, UTC window, availability, conditional number. |
| Risk | Implemented | Exposure/stop/take/trailing, holding limit, loss cooldown, max daily entries, daily-loss/drawdown entry pauses and risk-to-stop sizing. No loss guarantee. |
| General state flag | Preview | Catalog only; execution rejected. |
| Microstructure nodes | Provider-required | Genuine spread/imbalance/OFI/depth/flow inputs; no price-proxy substitution. |
| Derivatives nodes | Provider-required | Funding/basis/mark/index/OI/ratio/premium/liquidation inputs and availability evidence absent. No hedged carry engine. |
| News/sentiment/AI-event nodes | Provider-required | No executable source. Intelligence page remains labelled fixtures. |
| ML prediction nodes | Provider-required | Real training examples exist; compatible as-of graph prediction adapter absent. |
| Short/leverage/portfolio | Unsupported | Explicit status; engine is unlevered single-asset long/cash. |
| Original historical data | Implemented, preserved | BTC/ETH/SOL 2022–2025 4h, 8,766 bars each; old IDs/hash semantics. |
| Intraday history | Implemented bounded scope | BTC January 2025 1m/5m/15m/1h; no all-year/cross-asset intraday claim. |
| Daily history | Implemented derived source | Complete UTC groups of six existing 4h bars, not a new official-daily acquisition. |
| Multi-timeframe inputs | Implemented constrained | Higher/equal supported sources, causal as-of completion/assumed availability, gaps. No smaller bars from larger candles. BTC-only intraday auxiliaries. |
| Synthetic demos | Implemented and labelled | Separate 4h/1d examples; no fallback. Missing quote volume disables VWAP. |
| Market terminal | Implemented | OHLC candles/volume, overlays, one selected oscillator pane, crosshair/pan/zoom/reset/autoscale/fullscreen, dates/provenance and saved indicator preferences. Eight series/5,000 candles maximum per request. |
| Financial renderer | Implemented adapter | Existing ECharts; no vendor feed or proprietary terminal. |
| Execution versions | Implemented | Schema 1 frozen i+2; schema 2 embargo default or explicitly optimistic next-open mode. |
| Decision trace | Implemented for v2 | Actual recorded node values/clocks/order IDs/events/account/risk state; chart/timeline inspection. Bounded dropped counts. No fabricated v1 traces. |
| Backtest/results | Implemented | Actual queued jobs, immutable inputs/results, warm-up/gaps/costs, accounting, analytics/export/provenance. |
| Diagnostics | Implemented descriptive | Fixed half/base/double costs or chronological thirds/sequential unchanged-policy replay; no tuning/refitting. |
| Run comparison | Implemented | Owner-scoped saved runs/support context. Unmatched populations are not paired evidence. |
| Uncertainty | Implemented descriptive | 1,000 week-cluster return-difference draws, seed 42; suppressed below 20 weeks; approximate unadjusted historical intervals. |
| Offline copilot | Implemented | Deterministic explanations labelled offline_rules; no fake conversational generation. |
| External copilot | Real adapter, default unconfigured | OpenAI Responses structured proposals, consent/evidence/budgets/timeouts/retry, conversations/diff/approval/rollback. No paid call implied. |
| Automatic AI edits | Disabled by design | Approval checks draft hash and creates an immutable version. Stale proposals conflict. |
| ML Studio | Implemented bounded example | Fixed logistic direction/ridge return, causal/nonoverlap/purged splits/training-only scaling, baseline/metrics/calibration/native JSON registry. |
| ML isolation | Implemented process limits | Fixed child Python, 256 MiB/30 CPU seconds/60 wall seconds, I/O caps/cancellation. No network adapter; no OS network sandbox. |
| Community | Implemented locally | Replay-equal publication, immutable snapshots/forks. No internet deployment. |
| Persistence | Implemented additive | Existing records retained; migration 004 adds studio tables; legacy dispatch/replay evidence. |
| Audit | Implemented locally | Owner auth/strategy/run/research/copilot/publication events; not operational security monitoring. |
| Bots/paper/live | Disconnected | Preview only; no account/worker/orders or fabricated P&L. |
| Billing/alerts/moderation | Deferred | No checkout, delivery or full moderation operations. |

A catalog entry can be executable while a chosen dataset lacks required fields. Historical assumed availability is not measured receipt/live freshness. Saved indicator/autoscale preferences are not a full drawing-tool or multi-window workspace system. Only one oscillator is displayed at a time.

Scenario “walk-forward” means fixed-policy chronological replay, not adaptive fitting. ML is a separate fixed experiment without validation-driven parameter selection. Repeated historical analysis stays retrospective. Executed evidence is under verification/v02/. See V02_DELIVERY.md and V02_MIGRATION.md; original verification remains historical 0.1 evidence.
