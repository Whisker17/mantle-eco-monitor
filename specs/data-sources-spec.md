# Data Sources and Update Frequency Specification

> All upstream refresh frequencies in this document were verified on 2026-03-17 by calling
> each API endpoint and analyzing timestamp intervals in the response data.
> Test script: `scripts/test_source_frequencies.py`

---

## 1. Core Metrics — Source and Refresh Summary

| # | Metric | Primary Source | API Endpoint | Verified Upstream Refresh | Our Scheduler Cadence |
|---|--------|---------------|--------------|---------------------------|----------------------|
| 1 | TVL | DefiLlama | `GET /v2/historicalChainTvl/Mantle` | **Daily** (exactly 1d intervals) | Every 8h (`core_defillama`) |
| 2 | Total Value Secured | L2Beat | `GET /api/scaling/tvs/mantle` | **~6h** (median 6h, min 2h) | Every 6h (`core_l2beat`) |
| 3 | Stablecoin Supply | DefiLlama | `GET stablecoins.llama.fi/stablecoincharts/Mantle` | **Daily** (exactly 1d intervals) | Every 8h (`core_defillama`) |
| 4 | Stablecoin Market Cap | DefiLlama | `GET stablecoins.llama.fi/stablecoinchains` | **Daily** (snapshot; follows stablecoincharts cadence) | Every 8h (`core_defillama`) |
| 5 | Chain Transactions | GrowThePie | `GET /v1/fundamentals.json` | **Daily** (exactly 1d intervals, ~1d lag) | Daily at 10:00 (`core_growthepie`) |
| 6 | MNT Market Cap | GrowThePie | `GET /v1/fundamentals.json` | **Daily** (same endpoint as above) | Daily at 10:00 (`core_growthepie`) |
| 7 | Daily Active Users | Dune | Execute saved query | **On-demand** (query-based) | Daily at 10:20 (`core_dune`) |
| 8 | Active Addresses | Dune | Execute saved query | **On-demand** (query-based) | Daily at 10:20 (`core_dune`) |
| 9 | Stablecoin Transfer Volume | Dune | Execute saved query | **On-demand** (query-based) | Daily at 10:20 (`core_dune`) |
| 10 | DEX Volume | DefiLlama | `GET /overview/dexs/Mantle` | **Daily** (chart: 1d intervals; `total24h` is rolling) | Every 8h (`core_defillama`) |
| 11 | MNT Volume | CoinGecko | `GET /api/v3/coins/mantle` | **~1–5 min** (real-time rolling; free tier ~5 min) | Every 6h (`core_coingecko`) |

---

## 2. Ecosystem Protocol Metrics — Source and Refresh Summary

| Metric | Protocol Types | Source | API Endpoint | Verified Upstream Refresh |
|--------|---------------|--------|--------------|---------------------------|
| TVL | All protocols | DefiLlama | `GET /protocol/{slug}` | **~Daily** (median 1d, min ~15h for protocol endpoints) |
| Volume | DEX protocols | DefiLlama | `GET /overview/dexs/Mantle` | **Daily** (chart: 1d intervals) |
| Volume history | DEX protocols | DefiLlama | `GET /summary/dexs/{slug}` | **Daily** |
| Supply | Aave V3 | DefiLlama | `GET /protocol/aave-v3` → `chainTvls.Mantle.tvl` | **~Daily** |
| Borrowed | Aave V3 | DefiLlama | `GET /protocol/aave-v3` → `chainTvls["Mantle-borrowed"].tvl` | **~Daily** |
| Utilization | Aave V3 | Derived | `borrowed / supply` | N/A (computed) |

---

## 3. Per-Source Detail

### 3.1 DefiLlama

| Property | Value |
|----------|-------|
| Base URLs | `https://api.llama.fi`, `https://stablecoins.llama.fi` |
| Authentication | None (public endpoints) |
| HTTP timeout | 30s |
| Rate limiting | No documented limit; staggered polling recommended |

**Endpoints and verified refresh cadence:**

| Endpoint | Metrics Provided | Verified Refresh | Evidence |
|----------|-----------------|------------------|----------|
| `/v2/historicalChainTvl/Mantle` | `tvl` (core) | **Daily** | 30 data points analyzed; median/min/max all = 1d exactly |
| `/stablecoincharts/Mantle` | `stablecoin_supply` | **Daily** | 30 data points analyzed; median/min/max all = 1d exactly |
| `/stablecoinchains` | `stablecoin_mcap` | **Daily** | Snapshot endpoint; no historical timestamps; follows same daily cadence as stablecoincharts |
| `/overview/dexs/Mantle` | `dex_volume` (core), per-protocol DEX volumes | **Daily** | Chart data: 30 points, all 1d intervals. The `total24h` field is a rolling aggregate updated more frequently but the chart data itself is daily |
| `/protocol/{slug}` | Protocol `tvl`, Aave `supply`/`borrowed` | **~Daily** | 28 points analyzed for aave-v3; median = 1d, min = 15.1h, mean = 23.7h |
| `/summary/dexs/{slug}` | Per-protocol DEX volume history | **Daily** | Same underlying daily aggregation as `/overview/dexs` |
| `/protocols` | Watchlist candidate list | **Continuous** | Protocol listing, not time-series data |

**Data format notes:**
- Timestamps are Unix epoch seconds (not milliseconds).
- TVL chart timestamps are midnight-aligned (00:00:00 UTC).
- Stablecoin chart timestamps are midnight-aligned.
- Protocol endpoints may have sub-daily data points near the latest entry (the most recent point reflects the last TVL snapshot rather than a midnight aggregate), but the historical series is daily.
- DEX `total24h` is a rolling 24-hour aggregate that updates more frequently than the chart series, but the chart data itself is daily snapshots at midnight UTC.

### 3.2 L2Beat

| Property | Value |
|----------|-------|
| Base URL | `https://l2beat.com/api` |
| Authentication | None (public, rate-limited in practice) |
| HTTP timeout | 30s |

**Endpoints and verified refresh cadence:**

| Endpoint | Metrics Provided | Verified Refresh | Evidence |
|----------|-----------------|------------------|----------|
| `/scaling/tvs/mantle` | `total_value_secured` | **~6h** | 30 data points analyzed; median = 6h, min = 2h, max = 6h, mean = 5.9h |

**Data format notes:**
- Response structure: `data.chart.data` → array of `[timestamp, native, canonical, external]`.
- `total_value_secured` = `native + canonical + external`.
- Timestamps are Unix epoch seconds.
- Data points are roughly 6-hour intervals but occasional 2-hour intervals appear, suggesting an adaptive refresh cadence.
- Latest data point at test time: 2026-03-17T14:00:00 UTC (within ~2h of test execution).

### 3.3 GrowThePie

| Property | Value |
|----------|-------|
| Base URL | `https://api.growthepie.com` |
| Authentication | None |
| HTTP timeout | 30s |

**Endpoints and verified refresh cadence:**

| Endpoint | Metrics Provided | Verified Refresh | Evidence |
|----------|-----------------|------------------|----------|
| `/v1/fundamentals.json` | `chain_transactions` (from `txcount`), `mnt_market_cap` (from `market_cap_usd`) | **Daily** | 30 data points analyzed; median/min/max all = 1d exactly |

**Data format notes:**
- Response is a flat JSON array; filter by `origin_key == "mantle"`.
- Date field is ISO-8601 string (`"2026-03-16"`), no timezone — treated as UTC.
- Data has a ~1-day lag: on 2026-03-17, the latest available data point was 2026-03-16.
- Available Mantle metric keys (verified): `aa_last7d`, `app_fees_usd`, `costs_blobs_usd`, `costs_l1_usd`, `costs_total_usd`, `daa`, `fdv_usd`, `fees_paid_usd`, `gas_per_second`, `market_cap_usd`, `stables_mcap`, `tvl`, `txcosts_median_usd`, `txcount`.
- We currently use `txcount` → `chain_transactions` and `market_cap_usd` → `mnt_market_cap`.

### 3.4 CoinGecko

| Property | Value |
|----------|-------|
| Base URL | `https://api.coingecko.com/api/v3` |
| Authentication | Optional; `x-cg-demo-api-key` header (env: `COINGECKO_API_KEY`) |
| HTTP timeout | 30s |
| Rate limiting | Free tier: ~10-30 calls/min; demo API key improves rate |

**Endpoints and verified refresh cadence:**

| Endpoint | Metrics Provided | Verified Refresh | Evidence |
|----------|-----------------|------------------|----------|
| `/coins/mantle` | `mnt_volume` (from `market_data.total_volume.usd`) | **~1–5 min** | `last_updated` field was 0.3 min behind request time at test |
| `/coins/mantle/market_chart?days=2` | Volume history (sub-daily) | **~Hourly** | 49 data points over 2 days; median interval = 60 min, min = 57.4 min |
| `/coins/mantle/market_chart?days=90&interval=daily` | Volume history (daily) | **Daily** | 91 data points over 90 days; median = 1d |
| `/ping` | Health check only | N/A | Availability probe |

**Data format notes:**
- The `/coins/mantle` snapshot endpoint refreshes very frequently (~minutes), but we collect from it every 6h.
- Market chart timestamps are in **milliseconds** (not seconds).
- CoinGecko auto-selects granularity based on the `days` parameter:
  - 1-2 days → ~hourly data points
  - 3-90 days → ~daily data points
  - \>90 days → ~daily data points
- Our collector uses `interval=daily` with `days=max` for historical backfill.

### 3.5 Dune

| Property | Value |
|----------|-------|
| Base URL | `https://api.dune.com/api/v1` |
| Authentication | Required; `X-Dune-API-Key` header (env: `DUNE_API_KEY`) |
| HTTP timeout | 30s |
| Rate limiting | Tier-dependent; "medium" performance tier used for queries |

**Endpoints and verified refresh cadence:**

| Endpoint | Purpose | Refresh Behavior |
|----------|---------|-----------------|
| `/query/{id}/results` | Cached results from last execution | **On-demand** — reflects when we last executed the query |
| `/query/{id}/execute` | Trigger fresh query execution | N/A — we initiate this |
| `/execution/{id}/status` | Poll execution status | N/A |
| `/execution/{id}/results` | Fetch completed results | N/A |

**Data freshness model:**

Dune does **not** have an inherent periodic refresh cycle. Data freshness depends on two factors:

1. **Blockchain indexing pipeline** — Dune indexes Mantle chain data with a delay of typically **a few minutes** behind the chain head.
2. **Query execution** — Cached results reflect the last time we (or anyone) ran the query. Our scheduler triggers execution daily at 10:20 Asia/Shanghai.

**Metrics and query IDs:**

| Metric | Env Var for Query ID | Data Granularity |
|--------|---------------------|------------------|
| `daily_active_users` | `DUNE_DAILY_ACTIVE_USERS_QUERY_ID` | Daily |
| `active_addresses` | `DUNE_ACTIVE_ADDRESSES_QUERY_ID` | Daily |
| `chain_transactions` | `DUNE_CHAIN_TRANSACTIONS_QUERY_ID` | Daily |
| `stablecoin_transfer_volume` | `DUNE_STABLECOIN_VOLUME_QUERY_ID` | Daily (with per-symbol breakdown) |

**Data format notes:**
- Query results contain `day` or `date` field as string (`"2026-03-16 00:00:00 UTC"`).
- Stablecoin volume query returns rows with `symbol`, `volume`, `tx_count` per stablecoin per day.
- DuneSyncService handles historical backfill with configurable lookback (`dune_sync_correction_lookback_days`, default 2).

---

## 4. Scheduler Cadence vs. Upstream Frequency

> All scheduler times below are in **Asia/Shanghai** timezone (UTC+8), as configured in `config/scheduler.toml`.
> Cadences were optimized on 2026-03-17 based on verified upstream frequencies.

| Job | Source | Our Cadence | Upstream Refresh | Match Assessment |
|-----|--------|-------------|-----------------|------------------|
| `core_defillama` | DefiLlama | Every 8h (02:30, 10:30, 18:30) | **Daily** | 3x/day for daily data; catches new data point within ~8h |
| `core_l2beat` | L2Beat | Every 6h (00:00, 06:00, 12:00, 18:00) | **~6h** | Exact match with upstream refresh cadence |
| `core_coingecko` | CoinGecko | Every 6h (03:15, 09:15, 15:15, 21:15) | **~1–5 min** (snapshot) | Under-polling — acceptable; MNT volume is low-urgency |
| `core_growthepie` | GrowThePie | Daily at 10:00 | **Daily** (~1d lag) | Exact match — 1 poll/day for daily data with 1-day lag |
| `core_dune` | Dune | Daily at 10:20 | **On-demand** | Good fit — daily-granularity data; correction lookback covers gaps |
| `eco_aave` | DefiLlama | Daily at 11:00 | **~Daily** | Exact match with upstream |
| `eco_protocols` | DefiLlama | Daily at 11:20 | **~Daily** | Exact match with upstream |
| `watchlist_refresh` | DefiLlama | Daily at 04:00 | **Continuous** (listing) | Good fit — protocol list changes slowly |
| `source_health` | All | Hourly at :45 | N/A | Operational probe |

### Design notes

- **`core_defillama`** collects all DefiLlama metrics (TVL + stablecoin + DEX) in a single job. Previously TVL was split into a separate hourly job (`core_defillama_tvl`), but since all DefiLlama data is daily, a unified 8h cadence is sufficient and reduces API calls from ~30/day to 3/day.

- **`core_coingecko` at 6h vs. ~minute-level upstream**: CoinGecko data is near-real-time, but MNT volume is not a critical alerting metric. Polling every 6h is a deliberate trade-off between API rate budget and data freshness.

---

## 5. Source Authentication Summary

| Source | Auth Required | Env Var | Impact if Missing |
|--------|--------------|---------|-------------------|
| DefiLlama | No | — | N/A |
| L2Beat | No | — | N/A |
| GrowThePie | No | — | N/A |
| CoinGecko | Optional | `COINGECKO_API_KEY` | Tighter rate limits on free tier; data still accessible |
| Dune | Yes | `DUNE_API_KEY` | Cannot execute queries; `daily_active_users`, `active_addresses`, `chain_transactions`, `stablecoin_transfer_volume` unavailable |

---

## 6. Data Lag Summary

| Source | Typical Lag | Notes |
|--------|------------|-------|
| DefiLlama (chain TVL) | ~0–24h | Daily data point appears sometime during the day for the current or previous UTC day |
| DefiLlama (stablecoin) | ~0–24h | Daily aggregation |
| DefiLlama (DEX chart) | ~0–24h | Daily aggregation; `total24h` rolling value has less lag |
| DefiLlama (protocol) | ~0–24h | Latest point may be sub-daily |
| L2Beat | ~2–6h | 6h refresh cycle, latest point was ~2h behind at test time |
| GrowThePie | **~1 day** | On 2026-03-17, latest available data was 2026-03-16 |
| CoinGecko | **~minutes** | Near-real-time snapshot |
| Dune | **Minutes** (indexing) + **our execution delay** | Blockchain indexing is near-real-time; total lag depends on when we run the query |

---

## 7. Verification Methodology

All frequencies were verified by running `scripts/test_source_frequencies.py` on 2026-03-17T15:59 UTC. The script:

1. Called each API endpoint using `httpx.AsyncClient` with a 30s timeout.
2. Extracted the last 30 data points from each time-series response.
3. Computed the interval (in seconds) between consecutive timestamps.
4. Reported median, min, max, and mean intervals.
5. For snapshot endpoints (CoinGecko `/coins/mantle`, DefiLlama `/stablecoinchains`), compared `last_updated` or current values against request time.
6. Dune was not tested (no `DUNE_API_KEY` in test environment) — its on-demand model is documented from the API design.

To re-run verification:

```bash
python scripts/test_source_frequencies.py
```

Set `DUNE_API_KEY` in the environment to include Dune in the test.
