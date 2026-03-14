from decimal import Decimal

import httpx
import pytest

from src.ingestion.coingecko import CoinGeckoCollector


@pytest.fixture()
def sample_coingecko_payload():
    return {
        "market_data": {
            "total_volume": {"usd": 95_000_000},
            "market_cap": {"usd": 2_500_000_000},
        }
    }


@pytest.fixture()
def coingecko_collector(sample_coingecko_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=sample_coingecko_payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return CoinGeckoCollector(http_client=client)


@pytest.mark.asyncio
async def test_coingecko_collector_maps_mnt_metrics(coingecko_collector):
    records = await coingecko_collector.collect()

    assert len(records) == 1
    names = {r.metric_name: r.value for r in records}
    assert names["mnt_volume"] == Decimal("95000000")
    assert all(r.entity == "mantle" for r in records)
    assert all(r.scope == "core" for r in records)


def test_coingecko_source_platform():
    collector = CoinGeckoCollector()
    assert collector.source_platform == "coingecko"
