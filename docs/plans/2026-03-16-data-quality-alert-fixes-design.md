# Data Quality Alert Fixes Design

**Date:** 2026-03-16
**Status:** Approved in discussion on 2026-03-16.

## Goal

Fix the current false-alert and protocol-selection problems by tightening window comparison rules, correcting protocol metric semantics, replacing the dynamic ecosystem watchlist with an explicit fixed list, and defining a safe historical rebuild path.

## Root Causes Confirmed

### 1. Window comparisons are not coverage-aware

`get_comparison_snapshot()` currently selects the earliest snapshot inside a window without checking whether the window is actually well-covered. This creates several bad outcomes:

- metrics with only 2 rows can still produce `7D` alerts
- `7D` and `MTD` can collapse to the same anchor when only one prior row exists in both windows
- sparse monthly history can still produce `MTD` alerts

### 2. Missing dates can distort movement calculations

The system does not interpolate missing days, which is correct, but it also does not suppress alerts when history is too sparse. As a result, gaps can create misleading percentage changes and false threshold alerts.

### 3. Aave TVL derivation is invalid for current upstream data

The current `AaveAdapter` derives TVL as `supply - borrowed`. Current DefiLlama Mantle values can produce `borrowed > supply`, which leads to negative TVL snapshots and absurd decline alerts.

### 4. DAU and active addresses in the current database are still legacy data

The exported CSV shows `daily_active_users` and `active_addresses` are still identical Growthepie-backed series. This is expected for an old database state and means code changes alone are not enough; affected history must be rebuilt.

### 5. Ecosystem protocol selection is still dynamic

The current watchlist manager still ranks protocols by score and fills dynamic slots. This does not match the desired curated Mantle protocol set.

## Approved Comparison Rules

### General principle

Manual snapshot insertion remains fully allowed. Coverage rules only decide whether a windowed alert may be generated; they do not block writes.

### `7D` alerts

Allow `7D` threshold and decline comparisons only when:

- the series spans back to at least `current_day - 7`
- the most recent 8 natural days contain data for at least 6 days

Otherwise:

- store snapshots normally
- skip `7D` alert generation

### `MTD` alerts

Allow `MTD` threshold and decline comparisons only when:

- the first snapshot in the month is no later than day 2 of the month
- monthly day coverage from month start through current day is at least 80%

Otherwise:

- store snapshots normally
- skip `MTD` alert generation

### Missing data policy

Do not interpolate, forward-fill, or synthesize missing values. Missing history should suppress window-based alerts rather than invent anchor points.

## Approved Aave Behavior

Keep monitoring all four Aave metrics:

- `tvl`
- `supply`
- `borrowed`
- `utilization`

But change Aave TVL semantics:

- `supply`, `borrowed`, and `utilization` remain derived from chain-specific Mantle entries
- `tvl` is no longer computed as `supply - borrowed`
- `tvl` should be read directly from DefiLlama’s protocol-level TVL series for `aave-v3`, using the normal protocol TVL path

This preserves the desired Aave metric set while preventing negative TVL artifacts.

## Approved Ecosystem Watchlist

Replace dynamic ranking with a fixed curated list:

- `aave-v3`
- `cian-yield-layer`
- `mantle-index-four-fund`
- `merchant-moe`
- `treehouse-protocol`
- `ondo-yield-assets`
- `agni-finance`
- `stargate-finance`
- `apex-omni`
- `compound-v3`
- `uniswap-v3`
- `init-capital`
- `woofi`
- `fluxion-network`

### Aggregated protocols

Some product-facing protocols should aggregate multiple DefiLlama slugs:

- `merchant-moe` = `merchant-moe-dex` + `merchant-moe-liquidity-book`
- `stargate-finance` = `stargate-v1` + `stargate-v2`
- `woofi` = `woofi-swap` + `woofi-earn`

### DEX volume rules

The following protocols collect both `tvl` and `volume`:

- `merchant-moe`
- `agni-finance`
- `uniswap-v3`
- `woofi`
- `fluxion-network`

For `woofi`, aggregated TVL should include `woofi-swap` and `woofi-earn`, while volume should come from `woofi-swap`.

## Historical Rebuild Strategy

The current database contains stale and semantically invalid data for some metrics. The system therefore needs an explicit rebuild path for affected series:

- `daily_active_users`
- `active_addresses`
- `mnt_volume`
- `tvl`
- fixed ecosystem protocol metrics
- Aave metrics

Manual data insertion remains supported, but rebuilt history should become the canonical basis for automated alerts.

The rebuild should:

- remove affected automated snapshots for targeted metric/entity pairs
- keep manual insertion capability intact
- re-run the appropriate collectors or sync jobs to repopulate the corrected history
- prevent alerts from firing until coverage rules are satisfied

## Alert Card Corrections

The current card renderer should keep the recent readability improvements, but it must also stop exposing impossible values that come from invalid upstream semantics. Once the data fixes above are applied, card movement and current values should reflect trustworthy inputs.

## Testing

Regression coverage should prove:

- low-history series do not generate `7D` or `MTD` alerts
- sparse-month series do not generate `MTD` alerts
- Aave TVL no longer goes negative from `supply - borrowed`
- the fixed watchlist contains exactly the approved protocols
- aggregated protocols produce the correct TVL and volume behavior
- manual snapshot insertion still works while coverage rules suppress premature alerts

## Non-Goals

- building a general interpolation framework
- adding a full-blown data-quality service or dashboard
- changing daily summary or bot reply card layouts
- removing the ability to insert manual snapshots
