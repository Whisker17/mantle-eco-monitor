# Lark Integration Design

> Design for adding environment-aware Lark delivery and bot querying to the Mantle monitor.

**Goal:** Add a Lark app integration so the service can push alerts, push AI-written daily summaries, and answer natural-language Lark bot queries with source URLs.

**Status:** Approved in discussion on 2026-03-15.

---

## Context

The current service already has the core Phase 1 primitives needed for a Lark integration:

- scheduled collectors persist `metric_snapshots`
- rule evaluation persists `alert_events`
- job execution persists `source_runs`
- the API exposes `alerts`, `metrics`, `watchlist`, and `health`
- scheduler profiles are already environment-aware through `config/scheduler.toml`

The codebase also already reserves `lark_delivery_enabled` in [config/settings.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/settings.py), but there is no actual Lark client, event callback endpoint, digest job, or bot query service yet.

## Requirements

The approved integration must support:

1. sending alert messages to Lark after alerts are persisted
2. sending a configurable daily summary to Lark
3. allowing users to `@bot` inside Lark and query the service in natural language
4. returning source URLs with bot responses and summary content
5. routing `dev` and `prod` traffic to different Lark chats
6. using a service-owned external LLM API key for summary generation and natural-language query handling

## Assumptions

- The integration uses a Lark app, not a webhook-only bot.
- The first version supports a single active environment value such as `dev` or `prod` via configuration.
- The default daily summary schedule is configurable and should summarize the previous natural day in `Asia/Shanghai`.
- LLM use is constrained to intent parsing and response generation. Database reads remain deterministic and local.

## Non-Goals

The first version does not need:

- multi-turn conversation memory
- slash commands or interactive forms
- live re-fetching from upstream data sources during bot queries
- AI-generated alert existence decisions
- open-ended web search or unrestricted agent behavior inside Lark

## Chosen Approach

Implement the Lark integration inside the existing FastAPI and scheduler service. Keep the database as the source of truth and treat Lark as a downstream delivery and interaction layer.

The service will have three distinct responsibilities:

1. **Notify:** send alert cards and daily summary cards to environment-specific chats
2. **Respond:** receive Lark message events and answer supported natural-language queries
3. **Track:** persist delivery and event-processing state so retries and deduplication are safe

This keeps the implementation aligned with the current architecture and avoids an unnecessary second service.

## Module Layout

Recommended new modules:

- `src/integrations/lark/client.py`
  - fetch and cache app access credentials
  - send Lark messages or cards
  - encapsulate timeout and retry handling
- `src/integrations/lark/signature.py`
  - validate callback signatures or verification tokens
  - handle challenge requests cleanly
- `src/integrations/lark/router.py`
  - expose the FastAPI callback endpoint
  - deserialize events and hand off to services
- `src/integrations/lark/cards.py`
  - build alert cards, summary cards, and bot reply cards from structured inputs
- `src/services/query_tools.py`
  - provide constrained local reads over `metric_snapshots` and `alert_events`
- `src/services/llm.py`
  - wrap the external LLM API in a small provider-neutral adapter
- `src/services/notifications.py`
  - deliver alert and summary messages to the correct Lark chat
- `src/services/daily_summary.py`
  - build the daily summary context from database state
  - call the LLM only for summarization
- `src/services/bot_query.py`
  - parse natural-language intents
  - execute supported local queries
  - synthesize the final answer with source URLs

## Configuration

The current settings model should expand to include:

- `LARK_DELIVERY_ENABLED`
- `LARK_BOT_ENABLED`
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `LARK_VERIFICATION_TOKEN`
- `LARK_ENCRYPT_KEY`
- `LARK_ENVIRONMENT`
- `LARK_ALERT_CHAT_ID_DEV`
- `LARK_ALERT_CHAT_ID_PROD`
- `LARK_SUMMARY_CHAT_ID_DEV`
- `LARK_SUMMARY_CHAT_ID_PROD`
- `LLM_API_BASE`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`

Scheduler configuration should also gain a `daily_summary` job in [config/scheduler.toml](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/scheduler.toml):

- `prod`: fixed cron time in `Asia/Shanghai`
- `dev_live`: `manual`
- `ci`: `disabled`

## Delivery Tracking

The notification layer needs persistent delivery state instead of fire-and-forget logging.

Add a lightweight `delivery_events` table with fields similar to:

- `channel` such as `lark_alert` or `lark_summary`
- `entity_type` such as `alert` or `summary`
- `entity_id` for alert-backed deliveries, nullable for digest-style keys
- `logical_key` or idempotency key, unique per delivery target
- `environment`
- `status`
- `attempt_count`
- `last_error`
- `delivered_at`
- `created_at`
- `updated_at`

This table allows:

- safe retries
- protection against duplicate sends after scheduler retries
- operational visibility for failed deliveries

Lark callback events should also be deduplicated by event id or message id before processing.

## Alert Delivery Flow

The alert path should remain:

1. collector runs
2. snapshots are inserted
3. rule engine evaluates inserted snapshots
4. alert candidates are persisted to `alert_events`
5. transaction commits

Only after commit succeeds should the service attempt to send Lark alert cards.

The notification service should:

- load the newly created alert rows
- resolve the correct environment chat id for the `alert` channel
- create a delivery record
- send the card
- mark the delivery as `delivered` or `failed`

If Lark delivery fails, the collection job still succeeds. The database record is the truth; Lark is best-effort downstream delivery.

## Daily Summary Flow

Add a dedicated `daily_summary` scheduler job.

At the configured time, the summary service should:

1. compute the previous natural-day window in `Asia/Shanghai`
2. query key `metric_snapshots` and important `alert_events` within that window
3. construct a structured summary context containing:
   - core metric highlights
   - major changes
   - important alerts
   - source URLs
4. call the LLM to compress and prioritize the summary
5. render a Lark card
6. deliver it through the notification service

The service, not the LLM, computes all metric values and source lists. The LLM only improves ordering and wording.

## Bot Query Flow

Users will interact with the bot by `@` mention and natural language.

The event flow should be:

1. Lark sends a message callback to the FastAPI endpoint
2. the endpoint validates and deduplicates the event
3. the bot query service extracts the user message
4. the LLM performs **intent parsing only**, returning a constrained JSON structure
5. local query tools execute the supported database reads
6. the LLM synthesizes a human-readable answer from structured results
7. the service replies in Lark with the answer and source URLs

Supported first-version query classes:

- latest metric value
- metric history over a supported window
- recent alerts
- recent changes for a specific protocol or scope
- today or yesterday summary
- source lookup for a metric or alert

Unsupported prompts should get a bounded fallback response listing supported query categories.

## LLM Constraints

The LLM layer has two contracts.

### Intent Parsing

Input:

- raw user message
- supported intents
- allowed metric names, scopes, and windows

Output:

- strict JSON
- `unsupported` when the message falls outside the supported surface

The model must not generate SQL, tool names, or external fetch instructions.

### Answer Synthesis

Input:

- structured query results
- timestamps and time windows
- source URLs

Output:

- concise answer text
- no new facts not present in the structured payload

This keeps numerical correctness inside deterministic application code.

## Error Handling

The integration must explicitly handle:

- Lark credential fetch failures
- Lark send failures and non-2xx responses
- callback verification failures
- duplicate callback delivery
- LLM timeout or malformed JSON from intent parsing
- unsupported or underspecified user requests

Required behavior:

- alert and summary generation never roll back persisted monitoring data
- duplicate callback events do not generate duplicate replies
- malformed LLM output falls back to a fixed unsupported-response template
- failures are recorded in logs and delivery tracking rows

## Testing Strategy

Add test coverage at four layers.

### Unit Tests

- Lark token fetch and send payload construction
- signature verification and challenge handling
- chat routing by environment and channel
- card rendering
- summary context aggregation
- intent parsing result validation

### Service Tests

- alert delivery after persisted alerts
- delivery failure does not fail the collection job
- summary generation includes source URLs
- bot queries return deterministic data plus source URLs

### API Tests

- callback challenge request
- invalid callback rejection
- valid message event dispatch

### Scheduler and DB Tests

- `daily_summary` schedule registration per profile
- `delivery_events` migration, model, and repository behavior
- runtime integration around alert fan-out

## Rollout Notes

Recommended rollout order:

1. add config and delivery tracking
2. add the Lark client and card builders
3. wire alert delivery
4. add the daily summary job
5. add bot query support
6. validate in `dev` with isolated Lark chat ids
7. promote to `prod` chat ids only after delivery and duplicate-handling look stable
