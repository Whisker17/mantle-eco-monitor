# Dune Historical Sync Design

## Goal

Make `ATH`, `all_time`, `7d`, and `MTD` calculations for Dune-backed Mantle metrics reliable by storing a complete local daily history, supporting precise catch-up after downtime, and allowing upstream historical corrections to overwrite stale values.

## Current Constraints

- [`src/ingestion/dune.py`](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/ingestion/dune.py) only calls `get_latest_result()` and assumes the query already contains the needed history window.
- Current Dune SQL files in [`queries/dune`](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/queries/dune) hard-code a recent time window such as the last 30 days instead of accepting an explicit sync range.
- [`src/db/repositories.py`](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/db/repositories.py) deduplicates snapshots by day and skips duplicates entirely, so corrected historical values can never replace previously inserted rows.
- [`src/db/repositories.py`](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/db/repositories.py) computes `ATH` from the local `metric_snapshots` table, so incomplete history directly produces incorrect alerts and comparisons.
- [`src/main.py`](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/main.py) has a clean startup boundary today: it starts the scheduler and returns. Blocking startup on a full Dune backfill would make service availability depend on Dune latency and query success.

## Chosen Approach

Add a Dune historical sync pipeline that runs in the background after service startup and on schedule.

- Keep Dune queries split by metric family instead of merging them into one large SQL file.
- Parameterize each query with `start_date` and `end_date` so the application can request an exact daily range.
- Persist per-metric sync state in a dedicated table.
- Change snapshot writes from "insert if missing" to daily `upsert`, so corrected values replace stale rows.
- Treat bootstrap backfills and multi-day catch-up syncs as data-repair operations, not alert replay operations.

This keeps the local database as the source of truth for historical analytics while avoiding cold-start failures and repeated full-history scans.

## Scope

This design applies to Dune-backed core Mantle metrics that need historical continuity:

- `daily_active_users`
- `active_addresses`
- `chain_transactions`
- `stablecoin_transfer_volume`
- `stablecoin_transfer_tx_count`

It does not replace the existing public-source collectors for metrics already sourced from DefiLlama, Growthepie, L2Beat, or CoinGecko. It only improves the Dune-backed slice of the core metric set.

## Data Model

### `metric_snapshots`

Daily uniqueness needs to be enforceable in both PostgreSQL and SQLite-based tests. The simplest portable way to do that is to store a normalized daily key directly on the snapshot row.

- Add `collected_day` as a UTC `date` derived from `collected_at`.
- Add a unique constraint on `scope + entity + metric_name + collected_day`.
- Keep `collected_at` for exact timestamp provenance and API responses.
- Update repository writes to perform `upsert` by the new unique key.

This preserves the existing read path while making daily overwrite semantics explicit and portable.

### `metric_sync_states`

Add a new table keyed by `source_platform + scope + entity + metric_name`.

Required fields:

- `source_platform`
- `scope`
- `entity`
- `metric_name`
- `last_synced_date`
- `last_backfilled_date`
- `backfill_status`
- `last_sync_status`
- `last_error`
- `created_at`
- `updated_at`

This table records progress and lets the application distinguish between:

- a metric that has never been initialized
- a metric that was partially backfilled
- a metric that is healthy and only needs incremental catch-up
- a metric that failed on the previous attempt

## Sync Semantics

### Bootstrap Backfill

The first time a metric is enabled, the system creates a sync-state row and runs a historical backfill from the configured metric start date through the latest fully completed UTC day.

- Backfills must be chunked by time range, for example monthly or quarterly.
- Progress is advanced after each successful chunk, not only at the very end.
- If a chunk fails, the metric keeps its prior checkpoint and retries later.

### Incremental Catch-Up

After bootstrap completes, every sync run computes the next missing interval from `last_synced_date + 1` through the latest fully completed UTC day.

Example:

- last synced day: `2026-03-10`
- service restarts on `2026-03-13`
- latest fully completed UTC day: `2026-03-12`
- catch-up interval: `2026-03-11` through `2026-03-12`

This guarantees that downtime gaps can be recovered even if the service was offline during those days.

### Correction Window

The system accepts Dune historical corrections. Every sync run therefore includes a small correction lookback window in addition to the missing range.

Example:

- `last_synced_date = 2026-03-10`
- correction lookback = 2 days
- computed fetch start = `2026-03-09`

Rows in the lookback window are written with daily `upsert`, so corrected values replace the existing snapshot for that day.

## Dune Query Contract

Each Dune SQL file must accept the same application-level contract:

- input parameters: `start_date`, `end_date`
- output sorted by `day ASC`
- one row per day for single-metric outputs
- one row per `day + dimension` for multi-row metrics such as stablecoin breakdown

Required outputs:

- `queries/dune/daily_active_users.sql`: `day`, `value`
- `queries/dune/active_addresses.sql`: `day`, `value`
- `queries/dune/chain_transactions.sql`: `day`, `value`
- `queries/dune/stablecoin_transfer_volume.sql`: `day`, `symbol`, `volume`, `tx_count`

The application should stop relying on fixed "last 30 days" SQL filters. The query range must come from the sync service.

## Runtime Flow

### Startup

Startup should remain non-blocking.

- FastAPI startup still initializes the scheduler and returns.
- After scheduler startup, the app kicks off one background Dune sync task.
- This startup sync performs bootstrap or catch-up based on `metric_sync_states`.

If Dune is slow or unavailable, the API still comes up and the sync job records failure state for later retry.

### Scheduled Operation

The existing Dune job becomes a sync-aware job instead of a plain `collector.collect()` call.

- The job iterates configured Dune metrics independently.
- Each metric loads its sync state, computes the fetch interval, executes its Dune query, and upserts rows.
- One metric failing does not block other metrics from syncing.
- Source-run logging continues to record success or failure at the job level.

## Alert Behavior

Backfills and multi-day catch-up runs should not replay historical alerts.

- Initial bootstrap backfills are always silent.
- Catch-up runs with a backlog greater than one missing day are also silent.
- Normal steady-state syncs may evaluate alerts only when a run advances exactly one new completed day.
- Pure correction-only rewrites do not trigger alert evaluation.

This preserves data correctness without sending a burst of stale alerts after downtime.

## Failure Handling

Failure handling is per metric and per chunk.

- Persist chunk progress after every successful write batch.
- Do not advance `last_synced_date` for failed chunks.
- Record the last error on the sync-state row.
- Retry from the last successful checkpoint on the next run.

This makes sync behavior resumable and observable instead of opaque.

## Configuration

Add explicit configuration for each Dune metric query ID instead of overloading a single setting:

- `dune_daily_active_users_query_id`
- `dune_active_addresses_query_id`
- `dune_chain_transactions_query_id`
- `dune_stablecoin_volume_query_id`

Add sync tuning settings:

- `dune_sync_correction_lookback_days`
- `dune_sync_chunk_days`
- optional per-metric bootstrap start dates if the defaults should differ

## Testing Strategy

Add tests for each layer that the design changes:

- model and migration tests for `metric_sync_states`, `collected_day`, and the daily uniqueness constraint
- repository tests for daily `upsert` and sync-state progress helpers
- Dune client and collector tests for parameterized range fetching and result mapping
- runtime or service tests for bootstrap, catch-up, and correction-window logic
- startup and scheduler tests proving the app triggers a background Dune sync without blocking startup
- alert tests proving bootstrap and multi-day catch-up remain silent

## Non-Goals

- Replacing non-Dune data sources for already-covered metrics
- Replaying or backfilling historical Lark notifications
- Building a generic sync framework for every source in this iteration
