# Public Source First Data Strategy Design

**Date:** 2026-03-14

**Goal:** Replace the original Dune-first collection strategy with a public-source-first strategy that maximizes DefiLlama, Growthepie, and L2Beat coverage before falling back to other sources.

## Summary

Phase 1 should prefer public, unauthenticated endpoints wherever the metric semantics remain acceptable. The working product assumption for this revision is that `daily_active_users` and `daily_active_addresses` may be treated as the same metric in Phase 1, using Growthepie `daa`.

This design supersedes the source selection described in sections 3.1, 3.2, and 3.3 of `specs/DESIGN.md`.

## Source Decision

- DefiLlama remains the primary source for chain TVL, stablecoin supply, stablecoin market cap, chain-level DEX volume, and ecosystem protocol metrics.
- Growthepie becomes the primary public source for Mantle activity metrics that do not require Dune-specific SQL, specifically `daily_active_users`, `active_addresses`, and `chain_transactions`.
- L2Beat remains the primary source for `total_value_secured` and serves as a public comparison source for chain activity totals.
- CoinGecko remains useful for `mnt_volume`. Its use is optional for `mnt_market_cap` because Growthepie exposes a close public value.
- Dune is no longer the default source. Keep it only for metrics that the three public platforms do not cover cleanly, especially `stablecoin_transfer_volume`.

## Core Metric Matrix

| Metric | Primary Source | Endpoint | Notes |
|--------|----------------|----------|-------|
| TVL | DefiLlama | `GET https://api.llama.fi/v2/historicalChainTvl/Mantle` | Keep this distinct from L2Beat TVS and Growthepie TVL because the values diverge materially |
| Total Value Secured | L2Beat | `GET https://l2beat.com/api/scaling/tvs/mantle` | Sum of native, canonical, and external value as defined by L2Beat |
| Daily Active Users | Growthepie | `GET https://api.growthepie.com/v1/export/daa.json` or `fundamentals.json` | Phase 1 product assumption: `DAU == DAA` |
| Active Addresses | Growthepie | `GET https://api.growthepie.com/v1/export/daa.json` or `fundamentals.json` | Same source as `daily_active_users` in this phase |
| Stablecoin Supply | DefiLlama | `GET https://stablecoins.llama.fi/stablecoincharts/Mantle` | Use latest `totalCirculatingUSD.peggedUSD` |
| Stablecoin Market Cap | DefiLlama | `GET https://stablecoins.llama.fi/stablecoinchains` | Mantle row; Growthepie is comparison-only for now |
| Mantle Chain Transactions | Growthepie | `GET https://api.growthepie.com/v1/export/txcount.json` or `fundamentals.json` | L2Beat `activity.count` is a useful comparison source |
| Stablecoin Transfer Volume | Optional non-public fallback | No clean public endpoint confirmed in the public trio | Keep out of the public-source-first path |
| DEX Volume | DefiLlama | `GET https://api.llama.fi/overview/dexs/Mantle` | Chain-level daily DEX volume is publicly available |
| MNT Volume | CoinGecko | `GET https://api.coingecko.com/api/v3/coins/mantle` | Not covered by the public trio in current validation |
| MNT Market Cap | Growthepie | `GET https://api.growthepie.com/v1/fundamentals.json` | CoinGecko remains a fallback/reference source |

## Ecosystem Metric Matrix

| Protocol Type | Primary Source | Endpoint Pattern | Notes |
|---------------|----------------|------------------|-------|
| Aave V3 | DefiLlama | `GET https://api.llama.fi/protocol/aave-v3` | Use Mantle chain entries for supply, borrowed, utilization, and TVL |
| DEX protocols | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` and `GET https://api.llama.fi/summary/dexs/{slug}` | Use public protocol details plus public DEX summary |
| Non-DEX protocols | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` | TVL-only remains enough for Phase 1 unless special handling is required |
| Secondary lending | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` | Phase 1 keeps TVL-first behavior unless a protocol requires extra fields |

## Validated Public Coverage

The following public endpoints were directly checked on 2026-03-14:

- DefiLlama chain TVL returned `200` and exposed Mantle daily series.
- DefiLlama stablecoin endpoints returned `200` and exposed Mantle supply and market cap data.
- DefiLlama chain DEX overview returned `200` and exposed Mantle `totalDataChart` and `total24h`.
- DefiLlama protocol endpoints returned `200` at `/protocol/{slug}` for `aave-v3`, `merchant-moe-dex`, `merchant-moe-liquidity-book`, and `ondo-yield-assets`.
- Growthepie returned `200` from `api.growthepie.com` and exposed Mantle `daa`, `txcount`, `tvl`, `stables_mcap`, `market_cap_usd`, and other fundamentals.
- L2Beat returned `200` from `/api/scaling/tvs/mantle` and `/api/scaling/activity/mantle`.

## Semantic Differences

- DefiLlama `TVL` and L2Beat `TVS` are not interchangeable.
- DefiLlama chain TVL and Growthepie `tvl` also should not be treated as equivalent without additional methodology work. On 2026-03-12 they differed by nearly 3x.
- Growthepie `daa` is formally closer to active addresses than distinct human users. Phase 1 accepts this simplification by product decision.
- Growthepie `txcount` and L2Beat `activity.count` were close enough in spot checks to justify using Growthepie as the primary public chain transaction source.
- Growthepie `market_cap_usd` and CoinGecko market cap were close in spot checks, but not identical.

## Operational Constraints

- DefiLlama showed cache headers and tolerated repeated short bursts in manual checks. No explicit public rate-limit contract was located.
- Growthepie showed CDN cache headers and tolerated repeated short bursts in manual checks. The live domain is `api.growthepie.com`; the current `.xyz` domain in code returned `403`.
- L2Beat tolerated a few repeated requests, then returned `429 Too Many Requests` in a short burst. Treat it as rate-limited and cache aggressively.

## Implementation Consequences

- Update Growthepie collector base URL from `.xyz` to `.com`.
- Update L2Beat collector from the stale `/api/scaling/tvl/mantle` endpoint to current public endpoints.
- Update DefiLlama protocol collectors from `/api/protocol/{slug}` to `/protocol/{slug}`.
- Replace the Dune-first core metric ownership model with an explicit public-source matrix.
- Add one live coverage test for public endpoints and keep the existing unit tests fixture-based.

## Testing Strategy

- Add a live integration test that checks public endpoint reachability, basic field coverage, and expected Mantle metric ownership.
- Gate the live test behind an explicit marker so CI does not depend on public network stability by default.
- Keep unit tests for mapping and normalization local and deterministic.

## Out of Scope

- Automatic fallback switching between public sources.
- Formal reconciliation logic for differing TVL semantics across providers.
- Replacing CoinGecko for `mnt_volume` unless a public trio source becomes available.
- Replacing Dune for `stablecoin_transfer_volume` until a clean public source is identified.
