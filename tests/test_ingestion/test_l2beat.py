from decimal import Decimal

import httpx
import pytest

from src.ingestion.l2beat import L2BeatCollector


@pytest.fixture()
def sample_l2beat_payload():
    return {
        "success": True,
        "data": {
            "chart": {
                "data": [
                    [1710374400, 800_000_000, 200_000_000, 100_000_000, 3200],
                ]
            },
        },
    }


@pytest.fixture()
def l2beat_collector(sample_l2beat_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/scaling/tvs/mantle"
        return httpx.Response(200, json=sample_l2beat_payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return L2BeatCollector(http_client=client)


@pytest.mark.asyncio
async def test_l2beat_collector_maps_total_value_secured(l2beat_collector):
    records = await l2beat_collector.collect()

    assert len(records) == 1
    assert records[0].metric_name == "total_value_secured"
    assert records[0].value == Decimal("1100000000")
    assert records[0].entity == "mantle"
    assert records[0].scope == "core"
    assert records[0].unit == "usd"


def test_l2beat_source_platform():
    collector = L2BeatCollector()
    assert collector.source_platform == "l2beat"
