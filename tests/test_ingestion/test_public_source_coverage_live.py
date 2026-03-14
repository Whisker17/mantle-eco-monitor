import os
import time

import httpx
import pytest


LIVE_ENV_VAR = "RUN_LIVE_SOURCE_TESTS"


def _require_live_opt_in():
    if os.getenv(LIVE_ENV_VAR) != "1":
        pytest.skip(f"set {LIVE_ENV_VAR}=1 to run live public source coverage checks")


def _fetch_json(client: httpx.Client, url: str) -> object:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.get(url)
            if response.status_code == 429 and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # pragma: no cover - live diagnostic path
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise AssertionError(f"unreachable: failed to fetch {url}: {last_error}")


@pytest.mark.live
def test_public_sources_cover_required_metrics():
    _require_live_opt_in()

    with httpx.Client(
        headers={"User-Agent": "mantle-eco-monitor-live-tests/1.0"},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        defillama_tvl = _fetch_json(client, "https://api.llama.fi/v2/historicalChainTvl/Mantle")
        defillama_stablecoin_supply = _fetch_json(
            client, "https://stablecoins.llama.fi/stablecoincharts/Mantle"
        )
        defillama_stablecoin_mcap = _fetch_json(
            client, "https://stablecoins.llama.fi/stablecoinchains"
        )
        defillama_dex_volume = _fetch_json(client, "https://api.llama.fi/overview/dexs/Mantle")
        growthepie_fundamentals = _fetch_json(
            client, "https://api.growthepie.com/v1/fundamentals.json"
        )
        l2beat_tvs = _fetch_json(client, "https://l2beat.com/api/scaling/tvs/mantle")
        l2beat_activity = _fetch_json(client, "https://l2beat.com/api/scaling/activity/mantle")

    assert isinstance(defillama_tvl, list)
    assert defillama_tvl
    assert "tvl" in defillama_tvl[-1]

    assert isinstance(defillama_stablecoin_supply, list)
    assert defillama_stablecoin_supply
    assert "totalCirculatingUSD" in defillama_stablecoin_supply[-1]

    assert isinstance(defillama_stablecoin_mcap, list)
    mantle_chain = next(
        chain for chain in defillama_stablecoin_mcap if chain.get("name", "").lower() == "mantle"
    )
    assert mantle_chain["totalCirculatingUSD"]["peggedUSD"] >= 0

    assert isinstance(defillama_dex_volume, dict)
    assert defillama_dex_volume["chain"] == "Mantle"
    assert defillama_dex_volume["totalDataChart"] or defillama_dex_volume["total24h"] is not None

    assert isinstance(growthepie_fundamentals, list)
    mantle_metrics = {
        row["metric_key"]
        for row in growthepie_fundamentals
        if row.get("origin_key") == "mantle"
    }

    assert isinstance(l2beat_tvs, dict)
    assert l2beat_tvs["success"] is True
    assert l2beat_tvs["data"]["chart"]["data"]

    assert isinstance(l2beat_activity, dict)
    assert l2beat_activity["success"] is True
    assert l2beat_activity["data"]["chart"]["data"]

    discovered_covered_metrics = set()
    if defillama_tvl[-1].get("tvl") is not None:
        discovered_covered_metrics.add("tvl")
    if defillama_stablecoin_supply[-1].get("totalCirculatingUSD", {}).get("peggedUSD") is not None:
        discovered_covered_metrics.add("stablecoin_supply")
    if mantle_chain["totalCirculatingUSD"].get("peggedUSD") is not None:
        discovered_covered_metrics.add("stablecoin_mcap")
    if defillama_dex_volume["totalDataChart"] or defillama_dex_volume["total24h"] is not None:
        discovered_covered_metrics.add("dex_volume")
    if "daa" in mantle_metrics:
        discovered_covered_metrics.update({"daily_active_users", "active_addresses"})
    if "txcount" in mantle_metrics:
        discovered_covered_metrics.add("chain_transactions")
    if "market_cap_usd" in mantle_metrics:
        discovered_covered_metrics.add("mnt_market_cap")
    if l2beat_tvs["data"]["chart"]["data"]:
        discovered_covered_metrics.add("total_value_secured")

    required_covered_metrics = {
        "tvl",
        "total_value_secured",
        "daily_active_users",
        "active_addresses",
        "stablecoin_supply",
        "stablecoin_mcap",
        "chain_transactions",
        "dex_volume",
        "mnt_market_cap",
    }
    known_public_gaps = {"stablecoin_transfer_volume", "mnt_volume"}

    assert {"daa", "txcount", "market_cap_usd"} <= mantle_metrics
    assert "stables_mcap" in mantle_metrics

    # The public coverage matrix is an explicit contract for Phase 1.
    assert required_covered_metrics <= discovered_covered_metrics
    assert known_public_gaps.isdisjoint(discovered_covered_metrics)
    assert known_public_gaps == {"stablecoin_transfer_volume", "mnt_volume"}
