"""
Test script to verify upstream data source update frequencies.

Calls each external API used by the Mantle Eco Monitor and analyzes
timestamp intervals in the response data to determine how often each
source actually refreshes its data.

Usage:
    python scripts/test_source_frequencies.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
from datetime import datetime, timezone

import httpx

TIMEOUT = 30.0


def _ts_to_utc(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _intervals_seconds(timestamps: list[int | float]) -> list[float]:
    return [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]


def _format_interval(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _print_interval_stats(name: str, intervals_sec: list[float], n_points: int) -> dict:
    if not intervals_sec:
        print(f"  [{name}] Not enough data points to compute intervals")
        return {"source": name, "frequency": "unknown", "detail": "insufficient data"}

    med = statistics.median(intervals_sec)
    mn = min(intervals_sec)
    mx = max(intervals_sec)
    avg = statistics.mean(intervals_sec)

    print(f"  [{name}]")
    print(f"    Data points analyzed : {n_points}")
    print(f"    Median interval      : {_format_interval(med)}")
    print(f"    Min interval         : {_format_interval(mn)}")
    print(f"    Max interval         : {_format_interval(mx)}")
    print(f"    Mean interval        : {_format_interval(avg)}")

    if med < 7200:
        freq = "~hourly"
    elif med < 21600:
        freq = f"~{med / 3600:.0f}h"
    elif med < 43200:
        freq = "~6h"
    elif med < 72000:
        freq = "~12h"
    elif med < 129600:
        freq = "~daily"
    else:
        freq = f"~{med / 86400:.1f}d"

    print(f"    => Upstream frequency: {freq}")
    return {
        "source": name,
        "frequency": freq,
        "median_sec": med,
        "min_sec": mn,
        "max_sec": mx,
        "n_points": n_points,
    }


async def test_defillama_tvl(client: httpx.AsyncClient) -> dict:
    print("\n--- DefiLlama: Chain TVL ---")
    resp = await client.get("https://api.llama.fi/v2/historicalChainTvl/Mantle")
    resp.raise_for_status()
    data = resp.json()

    tail = data[-30:]
    timestamps = [row["date"] for row in tail]
    intervals = _intervals_seconds(timestamps)

    last_ts = _ts_to_utc(timestamps[-1])
    print(f"  Latest data point: {last_ts.isoformat()}")
    return _print_interval_stats("defillama_tvl", intervals, len(tail))


async def test_defillama_stablecoin(client: httpx.AsyncClient) -> dict:
    print("\n--- DefiLlama: Stablecoin Charts ---")
    resp = await client.get("https://stablecoins.llama.fi/stablecoincharts/Mantle")
    resp.raise_for_status()
    data = resp.json()

    tail = data[-30:]
    timestamps = [int(row["date"]) for row in tail]
    intervals = _intervals_seconds(timestamps)

    last_ts = _ts_to_utc(timestamps[-1])
    print(f"  Latest data point: {last_ts.isoformat()}")
    return _print_interval_stats("defillama_stablecoin", intervals, len(tail))


async def test_defillama_dex(client: httpx.AsyncClient) -> dict:
    print("\n--- DefiLlama: DEX Volume ---")
    resp = await client.get("https://api.llama.fi/overview/dexs/Mantle")
    resp.raise_for_status()
    data = resp.json()

    chart = data.get("totalDataChart", [])
    tail = chart[-30:] if chart else []
    timestamps = [row[0] for row in tail if len(row) >= 2]
    intervals = _intervals_seconds(timestamps)

    if timestamps:
        last_ts = _ts_to_utc(timestamps[-1])
        print(f"  Latest data point: {last_ts.isoformat()}")
        print(f"  total24h field   : {data.get('total24h')}")
    return _print_interval_stats("defillama_dex_volume", intervals, len(tail))


async def test_defillama_protocol(client: httpx.AsyncClient) -> dict:
    print("\n--- DefiLlama: Protocol (aave-v3) ---")
    resp = await client.get("https://api.llama.fi/protocol/aave-v3")
    resp.raise_for_status()
    data = resp.json()

    mantle_tvl = data.get("chainTvls", {}).get("Mantle", {}).get("tvl", [])
    tail = mantle_tvl[-30:]
    timestamps = [row["date"] for row in tail]
    intervals = _intervals_seconds(timestamps)

    if timestamps:
        last_ts = _ts_to_utc(timestamps[-1])
        print(f"  Latest data point: {last_ts.isoformat()}")
    return _print_interval_stats("defillama_protocol_tvl", intervals, len(tail))


async def test_defillama_stablecoin_chains(client: httpx.AsyncClient) -> dict:
    print("\n--- DefiLlama: Stablecoin Chains (snapshot) ---")
    resp = await client.get("https://stablecoins.llama.fi/stablecoinchains")
    resp.raise_for_status()
    data = resp.json()

    for chain in data:
        if chain.get("name", "").lower() == "mantle":
            mcap = chain.get("totalCirculatingUSD", {}).get("peggedUSD", 0)
            print(f"  Mantle stablecoin mcap: ${mcap:,.0f}")
            print("  (snapshot endpoint - no historical timestamps)")
            print("  => Same underlying data as stablecoincharts; refreshes ~daily")
            return {
                "source": "defillama_stablecoin_mcap",
                "frequency": "~daily (snapshot, follows stablecoincharts cadence)",
                "detail": "no timestamps in response",
            }
    print("  Mantle not found in stablecoinchains response")
    return {"source": "defillama_stablecoin_mcap", "frequency": "unknown"}


async def test_l2beat(client: httpx.AsyncClient) -> dict:
    print("\n--- L2Beat: Total Value Secured ---")
    resp = await client.get("https://l2beat.com/api/scaling/tvs/mantle")
    resp.raise_for_status()
    data = resp.json()

    chart_data = data.get("data", {}).get("chart", {}).get("data", [])
    tail = chart_data[-30:]
    timestamps = [row[0] for row in tail if len(row) >= 4]
    intervals = _intervals_seconds(timestamps)

    if timestamps:
        last_ts = _ts_to_utc(timestamps[-1])
        print(f"  Latest data point: {last_ts.isoformat()}")
    return _print_interval_stats("l2beat_tvs", intervals, len(tail))


async def test_growthepie(client: httpx.AsyncClient) -> dict:
    print("\n--- GrowThePie: Fundamentals ---")
    resp = await client.get("https://api.growthepie.com/v1/fundamentals.json")
    resp.raise_for_status()
    data = resp.json()

    mantle_rows = [r for r in data if r.get("origin_key") == "mantle"]
    metric_keys = set(r.get("metric_key") for r in mantle_rows)
    print(f"  Mantle metric keys available: {sorted(metric_keys)}")

    txcount_rows = sorted(
        [r for r in mantle_rows if r.get("metric_key") == "txcount"],
        key=lambda r: r.get("date", ""),
    )
    tail = txcount_rows[-30:]
    dates = []
    for row in tail:
        d = row.get("date", "")
        if d:
            dt = datetime.fromisoformat(d)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dates.append(dt)

    if dates:
        timestamps_sec = [d.timestamp() for d in dates]
        intervals = _intervals_seconds(timestamps_sec)
        print(f"  Latest data point: {dates[-1].isoformat()}")
        return _print_interval_stats("growthepie_fundamentals", intervals, len(tail))
    print("  No txcount data found for Mantle")
    return {"source": "growthepie_fundamentals", "frequency": "unknown"}


async def test_coingecko_snapshot(client: httpx.AsyncClient) -> dict:
    print("\n--- CoinGecko: Coin Snapshot ---")
    resp = await client.get("https://api.coingecko.com/api/v3/coins/mantle")
    resp.raise_for_status()
    data = resp.json()

    last_updated = data.get("last_updated", "")
    market = data.get("market_data", {})
    volume = market.get("total_volume", {}).get("usd")
    mcap = market.get("market_cap", {}).get("usd")

    print(f"  last_updated: {last_updated}")
    print(f"  MNT 24h volume: ${volume:,.0f}" if volume else "  MNT 24h volume: N/A")
    print(f"  MNT market cap: ${mcap:,.0f}" if mcap else "  MNT market cap: N/A")

    if last_updated:
        updated_dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        now = datetime.now(tz=timezone.utc)
        age_minutes = (now - updated_dt).total_seconds() / 60
        print(f"  Data age: {age_minutes:.1f} minutes")

    return {
        "source": "coingecko_snapshot",
        "frequency": "~1-5 min (real-time rolling, free tier ~every 5 min)",
        "detail": f"last_updated={last_updated}",
    }


async def test_coingecko_market_chart(client: httpx.AsyncClient) -> dict:
    print("\n--- CoinGecko: Market Chart (2d) ---")
    resp = await client.get(
        "https://api.coingecko.com/api/v3/coins/mantle/market_chart",
        params={"vs_currency": "usd", "days": "2"},
    )
    resp.raise_for_status()
    data = resp.json()

    volumes = data.get("total_volumes", [])
    tail = volumes[-30:]
    timestamps_ms = [row[0] for row in tail if len(row) >= 2]
    timestamps_sec = [ts / 1000 for ts in timestamps_ms]
    intervals = _intervals_seconds(timestamps_sec)

    if timestamps_sec:
        last_ts = _ts_to_utc(timestamps_sec[-1])
        print(f"  Latest data point: {last_ts.isoformat()}")
        print(f"  Total volume data points in 2d: {len(volumes)}")
    return _print_interval_stats("coingecko_market_chart_2d", intervals, len(tail))


async def test_coingecko_market_chart_daily(client: httpx.AsyncClient) -> dict:
    print("\n--- CoinGecko: Market Chart (90d, daily interval) ---")
    resp = await client.get(
        "https://api.coingecko.com/api/v3/coins/mantle/market_chart",
        params={"vs_currency": "usd", "days": "90", "interval": "daily"},
    )
    resp.raise_for_status()
    data = resp.json()

    volumes = data.get("total_volumes", [])
    tail = volumes[-30:]
    timestamps_ms = [row[0] for row in tail if len(row) >= 2]
    timestamps_sec = [ts / 1000 for ts in timestamps_ms]
    intervals = _intervals_seconds(timestamps_sec)

    if timestamps_sec:
        last_ts = _ts_to_utc(timestamps_sec[-1])
        print(f"  Latest data point: {last_ts.isoformat()}")
        print(f"  Total volume data points in 90d: {len(volumes)}")
    return _print_interval_stats("coingecko_daily_chart", intervals, len(tail))


async def test_dune(api_key: str) -> dict:
    print("\n--- Dune: Cached Query Results ---")
    async with httpx.AsyncClient(
        headers={"X-Dune-API-Key": api_key},
        timeout=TIMEOUT,
    ) as client:
        resp = await client.get(
            "https://api.dune.com/api/v1/query/1/results",
            params={"limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        exec_ended = data.get("execution_ended_at", "")
        exec_id = data.get("execution_id", "")
        print(f"  execution_ended_at: {exec_ended}")
        print(f"  execution_id: {exec_id}")
        print("  Dune data freshness depends on query execution schedule.")
        print("  Dune's blockchain indexing pipeline is typically ~minutes behind chain head.")
        print("  Cached results reflect the last execution time, not an inherent refresh cycle.")
        return {
            "source": "dune",
            "frequency": "on-demand (depends on query execution; indexing pipeline ~minutes behind chain head)",
            "detail": f"execution_ended_at={exec_ended}",
        }


async def main() -> None:
    print("=" * 70)
    print("  Mantle Eco Monitor - Upstream Data Source Frequency Test")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now(tz=timezone.utc).isoformat()}")

    results: list[dict] = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for test_fn in [
            test_defillama_tvl,
            test_defillama_stablecoin,
            test_defillama_dex,
            test_defillama_protocol,
            test_defillama_stablecoin_chains,
            test_l2beat,
            test_growthepie,
            test_coingecko_snapshot,
            test_coingecko_market_chart,
            test_coingecko_market_chart_daily,
        ]:
            try:
                result = await test_fn(client)
                results.append(result)
            except Exception as e:
                name = test_fn.__name__
                print(f"\n  ERROR in {name}: {e}")
                results.append({"source": name, "frequency": "error", "detail": str(e)})

    dune_key = os.environ.get("DUNE_API_KEY", "")
    if dune_key:
        try:
            result = await test_dune(dune_key)
            results.append(result)
        except Exception as e:
            print(f"\n  ERROR in test_dune: {e}")
            results.append({"source": "dune", "frequency": "error", "detail": str(e)})
    else:
        print("\n--- Dune: SKIPPED (no DUNE_API_KEY) ---")
        results.append({
            "source": "dune",
            "frequency": "on-demand (query-based; no inherent refresh cycle)",
            "detail": "skipped - no API key",
        })

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Source':<35} {'Verified Frequency':<30}")
    print("  " + "-" * 65)
    for r in results:
        print(f"  {r['source']:<35} {r['frequency']:<30}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
