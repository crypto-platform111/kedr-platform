# Bounded local ML research

KEDR 0.2 performs real small historical logistic-direction or ridge-return training in a separate fixed Python subprocess. The former draft workflow remains preserved. This implementation is a research/engineering example, not a new independently registered forecasting claim or automatic strategy provider.

## Inputs, clocks and splits

Select an available local dataset, dates within 2022–2025, target and horizon of 1–42 bars. Direction requires logistic; return requires ridge. Allowed fixed feature groups are momentum, volatility, calendar and volume through the API; the initial UI offers momentum/volatility/calendar. No user code, uploaded estimator, pickle, arbitrary path or hyperparameter search is accepted.

Features use completed candles and 42 complete past returns. Momentum uses 1/6/42-bar log price changes; variance uses 6/42-bar past log-return variance; calendar is known UTC hour/weekday harmonics; optional volume is earlier observed activity normalization. Exact names/formulas are saved with the native artifact. Training mean/population SD only, scale floor 1e-8 and fixed standardized clipping at ±5 apply.

Anchors are committed every horizon bars before support checks. Reference is open i+2 after a completed signal and five-second assumed availability; target is open i+2+horizon. Exact positive terminal log return means UP; zero is NOT UP. Return regression uses log-return bps. Full feature/target paths must be contiguous/valid. No gaps are interpolated and no label comes from daily-close substitution.

The split is fixed chronological 60/20/20 origins, followed by crossing-label purge and one-bar embargo. At least 120 complete nonoverlapping outcomes are required; retained splits require 60/20/20 rows. Direction additionally needs at least 10 per class in train and two per class in validation/test. Failure is saved, not repaired by moving boundaries. No validation selection or probability recalibration occurs.

## Fits and evidence

Logistic uses 400 fixed gradient steps, learning rate .15 and L2 gradient weight 1/n; intercept is unpenalized. Ridge uses alpha 1 with unpenalized intercept and a fixed native linear solve. There is one requested family, no tuning loop. The baseline is the earlier training UP frequency or mean return, scored on identical outcomes.

Saved outputs include split counts/cutoffs/exclusions, training/validation/test model and baseline metrics, predictions with exact clocks, fixed test probability bins for logistic, training coefficient associations and native JSON artifact. Logistic reports proper probability/discrimination metrics; regression reports return errors. Coefficients are not causal importance. The artifact stores weights/intercept/scaler/features/horizon/dataset hash/worker version/training-label end and is roundtrip-checked against saved test predictions.

Successful fits enter the owner model_registry with SHA256. An artifact explicitly records strategy_node_executable=false. There is no compatible as-of feature/prediction adapter yet; training never makes an ML node executable or deploys a model. Repeated historical trials remain exploratory, even with a chronological test score.

## Worker resources and cancellation

| Boundary | Fixed behavior |
| --- | --- |
| Candles | 100–20,000 source bars; choose a supported coarser dataset for the full minute month |
| Input/output | 16 MB input, 2 MB child output, 100 KB stderr, 3 MB saved result |
| Process | Fixed Python isolated-mode child, no arbitrary command/module |
| CPU/memory/wall | 30 CPU seconds, 256 MiB process memory, 60 wall seconds |
| Queue | One research worker/two admitted tasks; one pending/running per owner; 100 research records per owner |
| Cancellation | Registered process is terminated; cancellation status is preserved |
| Windows | Job Object memory/CPU/single-process/kill-on-close, fail closed on enforcement failure |
| Environment | Minimal runtime environment; parent API keys/session secrets omitted |

The worker has no network adapter but is not an OS network sandbox. It runs trusted fixed code rather than hostile user code. No GPU, auto-ML, arbitrary training service, distributed scheduler or prospective recorder is installed. Main backtests/scenarios still use bounded threads; subprocess hard limits apply to ML.

Files: research.py, process_runner.py, ml_worker.py and frontend/src/mlResearch.tsx. APIs include /api/ml/train, owner experiments/cancellation/model registry and research-job polling. Exact executed completion, resource/reload and preservation evidence belongs under verification/v02/, not an inferred “running” status.
