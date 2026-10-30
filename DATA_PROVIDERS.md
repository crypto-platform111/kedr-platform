# Market data, provider contracts and clocks

No market API key, network feed or download is required. Source selection is explicit; a failed historical adapter never falls back to generated prices.

## Available datasets

| IDs | Scope / provenance |
| --- | --- |
| demo_btc_4h, demo_eth_4h, demo_sol_4h | Original reproducible synthetic 2023 OHLCV, 2,190 bars each |
| verified_btc_4h, verified_eth_4h, verified_sol_4h | Original verified local Binance Spot 2022–2025, 8,766 bars and 48 ZIPs each |
| verified_btc_1m_2025_01 | One fixed existing BTC Spot January 2025 minute ZIP |
| verified_btc_5m_2025_01 / 15m / 1h | Strict UTC coarsening of that fixed minute month; IDs use the full timeframe, e.g. verified_btc_15m_2025_01 |
| verified_btc_1d, verified_eth_1d, verified_sol_1d | Complete six-bar UTC aggregation of the original historical 4h datasets |
| demo_btc_1d, demo_eth_1d, demo_sol_1d | Complete six-bar aggregation of labelled synthetic datasets |

Daily source here means aggregation, not the official daily source from the separate long-horizon quality study. Its source rules and hashes remain separate. New intraday data is BTC January 2025 only. ETH/SOL 1m/5m/15m/1h are not connected. Exact counts, source hashes, exclusions and available bounds come from dataset metadata/provenance.

Original historical adapters use the frozen cross_asset_200day_robustness/source_provenance.json manifest under KEDR_LEGACY_ROOT and confine paths to research/multiasset_trend/raw. The new minute adapter reads only BTCUSDT-1m-2025-01.zip identified by btc_long_horizon_direction/data_audit.json, confined to research/btc_volatility_trading_value/raw. It validates scope before decoding prices. No 2026 market ZIP, live DB or reserved data is read. No source is written.

Every selected ZIP passes retained SHA256 and CRC checks. Schema, positive ordered OHLC, volume, unique clocks, exact UTC grid and native duration quantum are checked. January 2025 original integer microseconds are normalized without rounding invalid opens. Canonical streams/manifests have separate hashes. A current-version checksum is not proof of original publication, receipt or no revisions.

## Data fields and aggregation

Bars retain UTC ISO time, integer millisecond timestamp, OHLC, base volume and valid flag. Historical four-hour bars additionally retain quote_volume and number_of_trades. The minute source also retains taker-buy base/quote volumes. Synthetic bars do not acquire invented historical quote volume.

Strict resampling only coarsens exact supported divisors. Every bucket must contain all expected valid aligned native bars; incomplete buckets are excluded with counts/reasons. Open/close use first/last, high/low use extrema, volume uses sums, and optional fields are summed only when present throughout. No interpolation, forward-filled missing bars or smaller candles from larger bars.

Rolling VWAP is sum quote volume / sum base volume; actual fields and complete support are mandatory. Missing inputs give an unavailable result, never a close-average proxy. Trade count likewise needs the real field.

## Availability and multiple sources

Schema-2 completed-candle availability defaults to completion + five seconds, **assumed**, not measured historical receipt. A higher-timeframe source is matched only after its own completion/availability at the base decision. A forming higher candle cannot enter an earlier signal. Cross-asset sources use exact supported local symbols/timeframes; intraday auxiliaries are BTC-only and cannot request smaller bars than the base.

MarketObservation and DatasetCoverage in market_providers.py provide future contracts for Spot/futures candles, settled/indicative funding, OI, mark/index, book snapshots/updates, aggregate trades, exchange-labelled liquidations, news/sentiment and cross-asset data. Fields include original timestamp/unit, event/period end, receipt/first-seen, availability basis/assumed lag, revision/version/acquisition clock, gaps/quality and source permission/redistribution status.

Unknown availability cannot declare an available_at clock. Receipt/first-seen eligibility cannot precede genuine capture. Assumed-lag eligibility needs its explicit lag and remains assumption-dependent. Liquidation records require exchange_labelled=true; price declines are not liquidations. These contracts do not connect a feed. Derivatives, microstructure, news and ML prediction strategy inputs remain unavailable.

## Execution modes and risks

- **V1 preserved:** four-hour long/cash, signal at completed i, execute open i+delay+1; minimum delay 1 means i+2.
- **V2 default full_bar_embargo:** completed candle plus assumed availability, same minimum i+2. Delay 1–6 is explicit.
- **V2 next_bar_open_optimistic:** open i+1, availability_seconds=0 and delay=1 required. Zero publication/decision latency is optimistic and not receipt-safe. This mode never rewrites old runs.
- Warm-up uses earlier completed native history, not future bars. Gaps reset indicator contexts. Cross-gap orders are cancelled; missing risk paths are not inferred as fills.
- Exit takes priority over simultaneous entry. No pyramiding. Exposure is allocation at entry, not a continuous rebalance guarantee.
- Static and bounded position-risk controls are explicit. Risk-to-stop sizing requires a stop and does not bound jump losses. Daily-loss/drawdown controls pause entries, not certify protection.
- OHLC stop/take/trailing paths lack exact intrabar sequencing. Conservative ordering applies, with worse gap-open stop references. Intrabar events carry interval precision instead of invented receipt/fill times. Trailing updates use causally committed levels.
- No shorts, leverage, borrowing, derivatives margin/funding/hedging, maker queue, historical lot/filter certification, live quotes or depth-based impact engine.

## Accounting and display

Fees and adverse slippage are configurable USDT assumptions per side. Equity marks cash plus inventory at completed closes. Terminal positions remain marked/open without fabricated liquidation or unexecuted exit fees. Gross return is same-quantity cost add-back, not a separately re-compounded zero-cost strategy. Closed-trade metrics exclude open positions.

The passive control uses matched execution/cost conventions and cash is constant. Risk/exposure need not match the strategy; a difference is not isolated timing alpha. CAGR/Sharpe can be null with insufficient span/variance/support. Clock, source, warm-up, gaps, cancelled/unfilled orders and hashes remain saved.

The chart API returns at most 5,000 actual candles/eight series, reports truncation, gaps, warm-up and unavailable indicators, and never randomly downsamples candles. Chart overlays and graph indicators share engine calculations. Historical simulation and all app ML results remain retrospective; repeated inspection is not independent validation.
