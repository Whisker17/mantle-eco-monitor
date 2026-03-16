# Activity Metric Semantics And Alert Card Design

**Date:** 2026-03-16
**Status:** Approved in discussion on 2026-03-16.

## Goal

Fix two related product issues:

1. `daily_active_users` and `active_addresses` currently do not represent distinct metrics.
2. Lark alert cards still do not match the intended PRD readability and formatting.

## Current Problem

### Activity Metric Semantics

The current Growthepie collector maps the same `daa` source value into both:

- `daily_active_users`
- `active_addresses`

This was an earlier Phase 1 simplification. It means the system currently stores two different metric names backed by the same underlying value series, which makes alerting and reporting misleading.

### Alert Card Presentation

The current alert card is structurally improved compared with the original implementation, but it still diverges from the approved product example:

- no emoji prefixes
- movement precision is too loose
- raw values can remain hard to scan
- detected time format does not match the desired presentation
- source should include both the readable source name and the URL

## Approved Metric Definitions

### Daily Active Users

`daily_active_users` will move to Dune and represent:

- distinct sending addresses on Mantle
- smoothed as a 7-day rolling average

This remains a proxy for users, not a strict human-user identity metric, but it is a more coherent and explainable definition than reusing Growthepie `daa` directly.

### Active Addresses

`active_addresses` will move to Dune and represent:

- distinct senders plus receivers on Mantle
- daily raw values, without smoothing

### Growthepie Scope

Growthepie will no longer emit:

- `daily_active_users`
- `active_addresses`

It will continue to emit:

- `chain_transactions`
- `mnt_market_cap`

## Approved Implementation Approach

### Dune Query Layer

The Dune query contract remains one row per day with `day` and `value`, but:

- `queries/dune/daily_active_users.sql` will compute the 7-day rolling average inside SQL
- `queries/dune/active_addresses.sql` will continue to return raw daily values

Keeping the smoothing in SQL avoids introducing special-case post-processing into the generic sync service.

### Sync And Alerting

`DuneSyncService` remains generic and unchanged in architecture:

- it still fetches rows for a date range
- maps them into snapshots
- writes them through the existing sync-state mechanism
- runs the same alert rules on the resulting snapshots

The only semantic change is that `daily_active_users` alerts will now evaluate against a smoothed Dune-derived series, while `active_addresses` alerts will evaluate against a raw daily Dune-derived series.

## Approved Alert Card Format

Alert cards keep the fixed PRD-inspired layout, but will be updated as follows:

- add emoji prefixes for title and each section
- keep movement precision to two decimal places
- format current values into human-readable compact units when needed
- show detected time as `Month D, YYYY - HH:MM SGT`
- render source as `Source Name (url)`

### Card Field Order

1. Title: directional emoji plus `MANTLE METRICS ALERT`
2. `Metric`
3. `Movement`
4. `Current Value`
5. `Status`
6. `Source`
7. `Detected`
8. `Suggested Draft Copy`
9. `Action Required`

### Value Formatting Rules

- Prefer existing human-ready `formatted_value` if it already looks readable.
- Otherwise compact numeric values into `K`, `M`, `B`, or `T`.
- Prefix approximate values with `~`.
- Preserve currency styling when the metric is clearly USD-denominated.

## Testing

Regression coverage will verify:

- Growthepie no longer emits `daily_active_users` or `active_addresses`
- Dune daily-active-users mapping uses the rolling-average query output
- Dune active-addresses mapping remains daily raw values
- alert cards include emoji, two-decimal movement, compact values, `SGT` timestamps, and source URL text

## Non-Goals

- redesigning daily summary cards
- redesigning bot reply cards
- changing alert rule thresholds
- introducing a fallback that silently swaps Dune failures back to Growthepie for these two metrics
