# News, first-seen clocks and sentiment integration

## Working now

`GET /api/news?symbol=BTCUSDT|ETHUSDT|SOLUSDT&locale=ru|en` serves two static educational records from `backend/app/providers.py:news_fixture`. The response is `mode=demo_fixture`, `is_current=false`; each article is `is_fixture=true`. The records demonstrate publication versus first-seen timestamps and the distinction between text sentiment and future returns. They are not current news, archived reporting, measured market catalysts or a live sentiment feed. Their dates are illustrative fixture values, not an actual receipt log. No source URL is invented for these educational records.

The interface supports Russian/English and symbol selection. The fixture labels are fixed examples, not outputs of an NLP model or evidence of a prediction. No news feed, scraper, scheduled ingestion job, article database, sentiment model or external summary service is running. Nothing is attached to strategy evaluation; `news_sentiment` remains an unavailable typed node.

`GET /api/providers` exposes this provider as `demo_fixture`, even if a future news credential is present. A key does not activate ingestion.

## Existing contracts

`backend/app/contracts.py` provides `NewsProvider.health()` and `articles(symbol, limit=20)`, and `SentimentProvider.health()` and `classify(article)`.

Its future `Article` boundary includes `id`, `source_url`, title, `published_at`, `first_seen_at`, `content_hash`, symbols and `is_fixture`. `SentimentObservation` includes article identity, `observed_at`, `model_version`, positive/negative/neutral label and optional score. The current UI fixture shape is intentionally smaller; a production adapter must map real records into the full contract rather than pretend the fixture already has source/capture provenance.

`ResearchAnalysisProvider` can later summarize real article evidence through an adapter. No dedicated connected AI-news-summary provider exists now. Any summary must retain article evidence links and its own model/template version rather than replace provenance with generated prose.

## Configuration names

`.env.example` reserves `KEDR_NEWS_PROVIDER=demo`, `KEDR_NEWS_API_KEY` and `KEDR_SENTIMENT_PROVIDER=disabled`. Only news-key presence is currently inspected for the configuration status flag; it does not initiate a call. Sentiment provider selection and real ingestion are future work. If an external AI summary is added, use the server-side AI adapter/configuration described in `AI_INTEGRATION.md`, with separate explicit news-summary capabilities and quotas.

Store credentials only in the backend process environment or a secret manager. Provider URLs and an API key must never be accepted from an arbitrary strategy node or exposed to the browser. No paid subscription is required for local use.

## Timestamp and revision requirements

An article's publisher timestamp is not proof that this platform had observed it then. Preserve UTC publisher `published_at` separately from locally recorded `first_seen_at` and each fetch/revision receipt. Record clock source, raw source timestamp and any parsing uncertainty. Keep publisher corrections and content hashes/version histories without silently moving availability backward. Missing first-seen evidence must remain unknown; importing an old article today does not make it historically point-in-time.

For future backtesting, the usable clock is no earlier than actual article receipt and completion/availability of the derived sentiment/summary. Do not join future revisions or a later generated summary at the original publisher timestamp. Historical APIs without receipt/version history support retrospective exploration only under explicitly stated assumptions. No such news backtest is activated here.

Use stable source/article identities, canonical URLs, content hashing and duplicate/near-duplicate detection. Preserve multiple publisher timestamps and receipts when syndication or corrections differ. Store asset/entity mapping and its version/confidence, including ambiguous ticker matches, rather than assume every occurrence of a symbol names the intended coin.

## Required ingestion and display controls

A future bounded server-side adapter needs an explicit source allow list, allowed URLs, TLS validation, request timeouts, size limits, retries/backoff, per-source/user quotas and health/outage reporting. Respect source licensing and retention terms. Escape/sanitize article content and links; treat text as untrusted evidence, not instructions to the model. Add evidence-linked structured summaries, publication/receipt badges and explicit unavailable states for missing fields.

Define source/article/revision and sentiment-observation persistence with ownership/access rules and migrations before ingestion. Record model version, label policy, confidence calibration if claimed, and classification completion time. Positive/negative text sentiment is not a future-return probability or recommendation. Scores must not be fabricated for providers that supply only labels.

Free feeds may support a later current-news experience, but no provider's market coverage, historical receipt quality or continuity is assumed from a long historical chart. External sources, live ingestion, sentiment models and AI news summaries remain disconnected in this release.
