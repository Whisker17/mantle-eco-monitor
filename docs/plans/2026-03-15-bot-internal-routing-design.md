# Bot Internal Routing Design

## Goal

Keep the Lark bot on a strict two-stage path:

1. Use the LLM only for intent analysis and argument extraction.
2. Route only to an explicit internal whitelist of query handlers.
3. For unsupported requests, do not execute anything and return an LLM-written constrained explanation.

## Context

The current bot already uses the LLM to parse user messages and then dispatches to a small set of internal query helpers. That shape is good, but the contract is still implicit:

- supported capabilities are not described precisely in code
- unsupported fallback text does not match the real capability set
- there is no explicit configuration boundary for future external actions
- the Lark bot runtime does not enforce its own enablement flag

The design needs to preserve the current "LLM first, internal route second" flow while making the safety boundary obvious in code and configuration.

## Approaches Considered

### 1. Replace LLM intent parsing with rule-based parsing

Pros:
- no model dependency for routing
- fully deterministic

Cons:
- not what the user requested
- loses natural-language flexibility

### 2. Keep LLM intent parsing and harden internal dispatch

Pros:
- preserves current UX
- keeps execution constrained to known internal handlers
- leaves room for later controlled expansion

Cons:
- still depends on the LLM for intent classification quality

### 3. Add generic tool-calling now, with soft policy restrictions

Pros:
- future-facing

Cons:
- too broad
- weakens the current safety boundary
- adds unnecessary complexity before the external-action model is designed

## Chosen Design

Use approach 2.

The bot remains a two-stage pipeline:

1. Intent extraction:
   - the LLM maps the message into a strict JSON shape
   - only known intents are accepted
2. Internal dispatch:
   - the application routes through a fixed intent-to-handler map
   - handlers only query internal persisted data
3. Response generation:
   - supported intents use the LLM to summarize only the returned internal JSON
   - unsupported intents use the LLM to generate a constrained explanation, but no action is executed

## Behavior Changes

### Supported behavior

The supported internal query intents remain:

- `metric_latest`
- `metric_history`
- `recent_alerts`

### Unsupported behavior

Unsupported requests:

- do not execute internal or external actions
- do not search the web
- do not invoke any future external tool path
- return an LLM-written explanation that clearly states the current supported capabilities

### Configuration boundaries

Add an explicit `bot_external_actions_enabled` setting with default `false`.

This setting does not enable any external actions yet. It exists only to reserve the boundary in code so future expansion does not silently bypass today's internal-only behavior.

Also enforce `lark_bot_enabled` at the callback layer so bot message handling can be disabled without removing the Lark app entirely.

## Data Flow

1. Lark event arrives.
2. Router validates callback token and bot enablement.
3. Bot query service asks the LLM for a structured intent payload.
4. Service validates the payload against the supported whitelist.
5. If supported:
   - route to the matching internal query helper
   - collect source URLs from returned internal data
   - ask the LLM to answer using only that JSON
6. If unsupported:
   - skip all internal and external action execution
   - ask the LLM for a constrained explanation message

## Error Handling

- If the bot is disabled, reject processing early.
- If LLM configuration is incomplete, fail closed for bot query handling rather than pretending to support requests.
- If the intent payload is invalid, treat it as unsupported.
- If no internal data is found for a supported query, return a constrained explanation instead of inventing an answer.

## Testing

Add focused tests for:

- unsupported fallback text generated through the LLM without executing actions
- supported requests still using internal query routing
- empty internal data paths not generating fabricated answers
- `lark_bot_enabled` enforcement
- new setting defaults and overrides

