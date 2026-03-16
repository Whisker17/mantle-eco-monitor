from datetime import date
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


@pytest.mark.asyncio
async def test_l2beat_collector_collect_history_filters_to_recent_90_day_window():
    payload = {
        "success": True,
        "data": {
            "chart": {
                "data": [
                    [1735516800, 10, 20, 30, 0],  # 2024-12-30
                    [1741132800, 11, 21, 31, 0],  # 2025-03-05
                    [1748908800, 12, 22, 32, 0],  # 2025-06-03
                ]
            },
        },
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    collector = L2BeatCollector(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    records = await collector.collect_total_value_secured_history(days=90, today=date(2025, 6, 3))

    assert len(records) == 2
    assert [record.value for record in records] == [Decimal("63"), Decimal("66")]
    assert all(record.metric_name == "total_value_secured" for record in records)


def test_l2beat_source_platform():
    collector = L2BeatCollector()
    assert collector.source_platform == "l2beat"
