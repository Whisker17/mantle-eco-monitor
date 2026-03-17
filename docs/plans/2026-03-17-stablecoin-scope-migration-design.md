# Stablecoin Transfer Scope Migration Design

**Date:** 2026-03-17
**Status:** Approved in discussion on 2026-03-17.

## Goal

Correct the database scope for token-level stablecoin transfer breakdown rows so they are stored under `stablecoin` instead of `core`, while leaving aggregated chain-level transfer rows and other stablecoin metrics unchanged.

## Problem

The Dune stablecoin transfer collector currently writes token-level rows such as:

- `entity = mantle:USDT`
- `entity = mantle:USDC`

with:

- `metric_name = stablecoin_transfer_volume`
- `metric_name = stablecoin_transfer_tx_count`

and `scope = core`.

That scope is too broad. These rows are not core chain metrics; they are token-level stablecoin breakdown data.

## Approved Scope Rules

### Rows that must move to `stablecoin`

Only rows matching all of the following should change:

- `scope = core`
- `entity LIKE 'mantle:%'`
- `metric_name IN ('stablecoin_transfer_volume', 'stablecoin_transfer_tx_count')`

These rows should become:

- `scope = stablecoin`

### Rows that must stay unchanged

The following remain as they are:

- aggregated transfer rows with `entity = mantle`
- `stablecoin_supply`
- `stablecoin_mcap`
- any non-stablecoin metrics

## Data Write Behavior

Future writes from the Dune stablecoin breakdown collector should use:

- `scope = stablecoin` for token-level rows like `mantle:USDT`
- `scope = core` for the aggregated chain-level `entity = mantle` transfer volume row

This preserves the distinction between:

- core chain-level metrics
- token-level stablecoin breakdown metrics

## Migration Strategy

Use an Alembic data migration.

This is preferred over an admin repair command because:

- it runs consistently across environments
- it is versioned alongside the code change
- it avoids manual post-deploy repair steps

The migration should update only the targeted rows described above.

## Query and Rule Impact

Existing stablecoin token-level alert suppression logic should continue to work because it keys primarily on:

- `entity.startswith("mantle:")`
- stablecoin transfer metric names

It should not rely on `scope = core`.

The chain-level aggregated transfer metric stays under `core`, so existing core-level query semantics remain intact.

## Testing Requirements

Regression coverage should prove:

- token-level stablecoin transfer records produced by Dune now use `scope = stablecoin`
- aggregated `entity = mantle` transfer volume still uses `scope = core`
- migration updates old token-level rows from `core` to `stablecoin`
- migration does not touch aggregated transfer rows or unrelated stablecoin metrics

## Non-Goals

- moving `stablecoin_supply` or `stablecoin_mcap` out of `core`
- changing stablecoin transfer metric names
- changing alert thresholds or suppression behavior
- rewriting historical values, timestamps, or entities
