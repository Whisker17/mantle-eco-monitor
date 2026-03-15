# Bot Readonly Whitelist Expansion Design

## Goal

Expand the Lark bot's internal whitelist so it can answer all suitable externally exposed read-only queries while still preserving the current execution boundary:

1. LLM parses intent and arguments.
2. Application routes only to explicit internal read-only handlers.
3. Unsupported or write-intent requests do not execute any action.

## Scope

The bot should support these read-only capabilities:

- latest metrics
- metric history
- alert queries
- health status
- source health
- watchlist
- daily summary

The bot should continue to reject write or state-changing requests, including:

- watchlist refresh
- alert review
- any future mutation endpoint

## Approaches Considered

### 1. Reuse HTTP route functions directly

Pros:
- fast to wire

Cons:
- couples bot behavior to API response shapes and request-layer dependencies
- harder to evolve cleanly

### 2. Reuse internal query/service layer behind a bot-specific intent map

Pros:
- keeps the LLM-to-handler boundary explicit
- lets HTTP API and bot share domain logic without sharing transport concerns
- easiest to keep read-only guarantees clear

Cons:
- requires a few new helper functions

### 3. Make the bot able to call any GET endpoint generically

Pros:
- broad coverage quickly

Cons:
- weakens control over parameter validation and response shaping
- invites accidental exposure of unsuitable endpoints later

## Chosen Design

Use approach 2.

The bot continues to use an explicit intent whitelist. We expand that whitelist with read-only intents that map to internal helper functions, not to HTTP routes directly.

## Intent Surface

The bot whitelist will support:

- `metric_latest`
- `metric_history`
- `alerts_list`
- `health_status`
- `source_health`
- `watchlist`
- `daily_summary`

`recent_alerts` can remain as a compatibility alias if needed, but the internal model should converge on `alerts_list` as the read-only alert query capability.

## Internal Query Layer

Add or extend query helpers so bot handlers can answer the full read-only set:

- latest metric helper
- metric history helper
- alert list helper with safe optional filters
- health status helper
- source health helper
- watchlist helper
- daily summary context helper

These helpers should only read persisted internal state.

## Data Flow

1. Lark message arrives.
2. LLM returns structured intent payload.
3. Payload is validated against the explicit read-only whitelist.
4. Matching handler runs a read-only internal helper.
5. LLM summarizes only the returned internal JSON.
6. Unsupported or mutation requests use the constrained fallback path and execute nothing.

## Error Handling

- Unsupported intents: constrained explanation only.
- Mutation-like intents: constrained explanation only.
- Missing internal data: constrained explanation only.
- DB errors: bubble as runtime failure; do not fabricate answers.

## Testing

Add focused tests for:

- new query helpers
- bot routing for each new read-only intent
- mutation-style requests staying unsupported
- no-data paths using constrained fallback

