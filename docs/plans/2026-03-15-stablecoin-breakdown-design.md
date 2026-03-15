# Stablecoin Breakdown Design

## Goal

Extend the existing Dune-backed stablecoin transfer ingestion so the system stores:

- daily transfer volume per stablecoin on Mantle
- daily transfer transaction count per stablecoin on Mantle
- daily total stablecoin transfer volume for Mantle

The design must fit the existing generic `metric_snapshots` model without introducing a new table.

## Current Constraints

- The system stores snapshots in a single `metric_snapshots` table keyed by `entity`, `metric_name`, and `collected_at`.
- The Dune collector currently expects rows shaped like `day + value` and maps them to a single `mantle / stablecoin_transfer_volume` metric.
- The rule engine evaluates every inserted snapshot unless code explicitly opts metrics out.

## Chosen Approach

Reuse the existing Dune collector and snapshot table, and represent per-token stablecoin data as additional entities.

- Keep `scope = "core"`.
- Use `entity = "mantle:<SYMBOL>"` for per-token rows, for example `mantle:USDT`.
- Store per-token volume as `metric_name = "stablecoin_transfer_volume"` with `unit = "usd"`.
- Store per-token transaction count as `metric_name = "stablecoin_transfer_tx_count"` with `unit = "count"`.
- Continue storing aggregate Mantle stablecoin volume as `entity = "mantle"` and `metric_name = "stablecoin_transfer_volume"`.

## Query Shape

The Dune SQL should return one row per `day + symbol`, including:

- `day`
- `symbol`
- `volume`
- `tx_count`

The SQL should:

- use a fixed address whitelist for the current top 6 Mantle stablecoins from DefiLlama
- exclude the current partially completed day
- exclude zero-address mint and burn transfers

## Collector Mapping

For each query row:

- emit one `MetricRecord` for `stablecoin_transfer_volume`
- emit one `MetricRecord` for `stablecoin_transfer_tx_count`

After processing all rows, aggregate the rows by day and emit one Mantle-level `stablecoin_transfer_volume` record per day.

## Alert Behavior

Per-token stablecoin detail snapshots should be stored but should not trigger alerts.

The implementation will skip alert evaluation when:

- `entity` starts with `mantle:`
- and `metric_name` is one of:
  - `stablecoin_transfer_volume`
  - `stablecoin_transfer_tx_count`

This preserves the current Mantle aggregate alert behavior while avoiding noisy token-level alerts.

## API Impact

No API schema changes are required.

The existing endpoints can already serve the new data:

- `/api/metrics/history?entity=mantle:USDT&metric_name=stablecoin_transfer_volume`
- `/api/metrics/history?entity=mantle:USDT&metric_name=stablecoin_transfer_tx_count`
- `/api/metrics/history?entity=mantle&metric_name=stablecoin_transfer_volume`

## Testing Strategy

- Add collector tests for the new Dune row shape and emitted records.
- Add a rule-engine test that per-token stablecoin detail does not produce alerts.
- Run targeted Dune ingestion and rule tests.
- Run a broader regression subset covering scheduler/runtime behavior.
