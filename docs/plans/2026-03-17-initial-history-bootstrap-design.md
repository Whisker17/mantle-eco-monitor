# Initial History Bootstrap Design

**Date:** 2026-03-17
**Status:** Approved in discussion on 2026-03-17.

## Goal

Make database initialization explicit and predictable:

- a manual bootstrap step seeds historical data into an empty or partially empty database
- daily scheduled collection only fetches the newest available data point
- Mantle chain `tvl` and all Dune-backed metrics retain full history
- all other supported historical metrics load only the most recent 90 days

This keeps the database useful for comparisons and charts without making ordinary daily jobs repeatedly backfill long history.

## Current Problems Confirmed

### 1. Initialization and daily collection are not separated

The current system has no dedicated bootstrap command. Historical seeding is split across ad hoc rebuild logic and source-specific behavior, while routine jobs still decide for themselves how much history to fetch.

### 2. Dune bootstrap currently happens on the normal runtime path

`DuneSyncService` treats missing sync state as a signal to bootstrap full history, and application startup currently triggers a background Dune sync. That conflicts with the desired model where initialization is manual and routine jobs only append the newest data.

### 3. Source behavior is inconsistent

- `DefiLlamaCollector` mostly collects only the latest point during regular jobs.
- `L2BeatCollector` reads a historical chart but only persists the newest row.
- `GrowthepieCollector` currently maps all returned dated rows during regular jobs.

This makes source behavior hard to reason about and causes different DB depth by source.

### 4. Ecosystem DEX volume history is chain-ambiguous for multichain protocols

For curated ecosystem DEXes such as `uniswap-v3` and `woofi`, the available DefiLlama protocol summary history is protocol-wide, not reliably Mantle-chain-only. Using that data for historical Mantle volume would silently change metric semantics.

## Approved Bootstrap Model

### Manual bootstrap command

Initialization will use a dedicated admin command instead of startup-time implicit backfills:

```bash
python -m src.admin bootstrap initial-history --apply
```

The command should support a dry-run preview when `--apply` is omitted, matching the existing admin patterns.

The bootstrap command must be idempotent. Re-running it should update same-day rows through existing snapshot upsert behavior rather than duplicating history.

### Bootstrap scope

Bootstrap loads historical data with the following policy:

- `core / mantle / tvl`: full history
- Dune-backed metrics: full history
- all other metrics with trustworthy historical endpoints: most recent 90 days

This includes core metrics and curated ecosystem protocol metrics.

## Source-Specific Rules

### DefiLlama core metrics

- `tvl`: full Mantle chain history from `historicalChainTvl/Mantle`
- `stablecoin_supply`: latest 90 days from `stablecoincharts/Mantle`
- `dex_volume`: latest 90 days from `overview/dexs/Mantle.totalDataChart`
- `stablecoin_mcap`: use the same chain-level USD stablecoin history as bootstrap input when a distinct chain historical market-cap endpoint is not exposed; this is an inference from DefiLlama's stablecoin history support and current chain-total USD output

Regular daily `core_defillama` jobs continue to fetch only the newest row for each metric.

### L2Beat

- `total_value_secured`: latest 90 days from `data.chart.data`

Regular daily `core_l2beat` jobs continue to fetch only the newest row.

### Growthepie

- bootstrap reads the full fundamentals payload and filters Mantle rows down to the newest 90 days
- routine `core_growthepie` jobs must no longer persist every returned dated row; they should persist only the newest available day per mapped metric

### CoinGecko

- `mnt_volume`: latest 90 days from `coins/mantle/market_chart`

Regular daily `core_coingecko` jobs continue to fetch only the newest row from the existing snapshot endpoint.

### Dune

Dune remains the only source that bootstraps full history during initialization, using the existing daily-history sync model.

However, that bootstrap must move behind the new explicit bootstrap command. Routine `core_dune` jobs should behave as incremental sync only and must not perform an implicit full bootstrap just because sync state is missing.

### Ecosystem protocols

- protocol `tvl`: newest 90 days for all curated ecosystem protocols
- protocol `volume`: newest 90 days only when the source history is chain-faithful for Mantle
- multichain DEX protocol `volume` history is intentionally skipped during bootstrap when only protocol-wide history is available

Daily `eco_protocols` jobs keep fetching only the latest Mantle-chain value.

This preserves the existing Mantle-only semantics for ecosystem DEX volume.

## Daily Collection Rules

After bootstrap:

- every scheduled source job fetches only the newest available data point
- same-day reruns continue to overwrite the same daily row through upsert logic
- no scheduled job performs long-range backfills
- no startup hook performs implicit history sync

This means:

- remove the startup-time background Dune sync
- keep the scheduler as the only routine collection entrypoint
- make bootstrap the only sanctioned path for historical initialization

## Architecture

### New bootstrap orchestration layer

Add a dedicated bootstrap service under admin code that orchestrates source-specific bootstrap collectors in a fixed order:

1. refresh curated watchlist
2. bootstrap core sources
3. bootstrap Dune full history
4. bootstrap ecosystem Aave metrics
5. bootstrap curated ecosystem protocol history

The orchestrator should use the existing `run_collection_job()` path where possible so DB writes, source run records, and alert evaluation stay consistent.

### Separate latest and history collectors

Collectors and protocol adapters should expose explicit history-oriented methods used only by bootstrap and rebuild flows. Existing `collect()` methods should remain the routine latest-only behavior.

This makes the caller choose the correct mode instead of relying on implicit source behavior.

## Alert and Data Semantics

- bootstrap writes real historical rows; it does not synthesize missing dates
- daily jobs keep the current upsert-by-day semantics
- `ATH` and `all_time` continue to use the local database, which is why full history is retained for Mantle chain `tvl` and all Dune metrics
- 90-day-limited metrics accept that `all_time` semantics are effectively bounded to the bootstrap retention window

## Testing Requirements

Regression coverage should prove:

- the new bootstrap CLI parses and previews correctly
- bootstrap collectors respect the full-history vs 90-day split
- routine collectors for L2Beat, Growthepie, DefiLlama core, CoinGecko, and ecosystem protocols only persist the newest point
- Dune no longer auto-bootstraps full history on the routine path
- startup no longer triggers background Dune collection
- multichain ecosystem DEX volume history is skipped during bootstrap while latest daily Mantle-chain volume remains intact

## Non-Goals

- changing alert thresholds or coverage rules
- adding a general retention policy for already-bootstrapped tables
- backfilling multichain ecosystem DEX volume with protocol-wide history
- moving initialization into Docker startup
