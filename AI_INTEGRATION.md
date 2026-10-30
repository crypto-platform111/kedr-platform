# Optional external copilot and offline explanations

KEDR 0.2 includes a real OpenAI Responses HTTPS adapter. It is **not connected by default** and no outbound request is made merely by opening the interface, supplying a key or asking for a local explanation.

## Local mode

Without a fully configured provider and explicit message consent, the drawer uses offline_rules: deterministic graph validation/summary or saved-run explanation. It does not invent conversational strategy generation or pretend a model answered. Selected saved-trade numbers and actual stored trace context can be attached as evidence; missing old traces are not reconstructed after the fact.

The guided rule builder remains local and creates the same typed graph independently of an AI provider.

## Configuration

Configure only the backend environment, using this project's .env.example:

- KEDR_AI_PROVIDER=openai
- KEDR_AI_API_KEY: private provider credential, never a frontend/VITE_ value.
- KEDR_AI_MODEL: an accessible operator-chosen model supporting Responses structured outputs. No model is silently selected.
- KEDR_AI_INPUT_USD_PER_MILLION and KEDR_AI_OUTPUT_USD_PER_MILLION: positive conservative operator-entered ceilings for that model. Zero keeps external AI disabled. Verify current official pricing separately; this release neither guesses nor automatically refreshes prices.
- Timeout, output-token, daily request/token/USD ceilings are explicit server settings.

Status is configured_unverified after complete configuration, not a claim of connectivity. Actual saved request status is reported separately. The provider has no web/tool access through this adapter. No paid request is authorized or sent during default installation/testing.

## Request and approval workflow

1. Start an owner-scoped conversation associated with a private strategy.
2. Review the message and consent checkbox. External consent sends the current specification/catalog, recent bounded conversation context and selected saved evidence to OpenAI.
3. The adapter sends to the fixed Responses endpoint with store=false and strict JSON schema. No arbitrary provider URL or generated-code runner exists.
4. The response contains reply, optional complete proposed_spec_json, exact numeric evidence references and limitations.
5. Server validation rejects invalid/incomplete/nonexecutable graphs, unsupported nodes and oversized outputs. Numeric prose digits are disallowed; structured numeric claims must exactly match supplied saved evidence. This reduces fabricated metrics but is not a guarantee of correct qualitative reasoning.
6. A valid proposal is saved as a preview with immutable before/after payloads and a diff. It cannot automatically edit the draft.
7. Approval requires the current draft's expected hash to equal the proposal baseline. A conflict returns 409 and applies nothing.
8. Approval creates another immutable strategy version. Rollback also creates a version, requires the approved draft hash and preserves every previous record.

## Budgets, retries and private storage

| Limit | Implementation default / bound |
| --- | --- |
| Timeout | 20 seconds, configurable 1–45 |
| Output | 2,500 tokens, configurable 256–6,000 |
| Daily owner requests | 20, configurable 1–100 |
| Daily owner tokens | 200,000, configurable 256–1,000,000 |
| Daily owner USD accounting | 1 USD, configurable 0.01–100 |
| Concurrency | One outbound request per owner; two globally |
| Message/context | 4,000 characters; 70,000 UTF-8 context bytes |
| Provider response | 400,000 bytes |
| Conversations | 100 per owner; bounded message history |
| Retry | At most once after explicit 429/502/503; transport timeout is not retried |

Before calling, SQLite atomically reserves a conservative byte-based input bound plus output and both possible attempts. Reservations remain accounted on success/failure/unknown timeout, so the dashboard is conservative local accounting, not a provider invoice. Actual returned usage is retained and can only increase accounted usage. A model's actual pricing exceeding configured ceilings would invalidate the monetary bound; use conservative current ceilings.

Conversations/proposals/usage stay in the local platform database and contain private research. Keys stay in backend process configuration, not responses or child ML environments. store=false does not erase local records or replace review of the provider's applicable data policies. No custom secret vault or at-rest encryption is supplied.

Implementation: backend/app/copilot.py; additive migration 004; frontend/src/copilot.tsx. Official structured-output reference: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses . Live model access was not established merely by implemented transport or stubbed tests.
