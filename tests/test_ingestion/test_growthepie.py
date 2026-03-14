from decimal import Decimal

import httpx
import pytest

from src.ingestion.growthepie import GrowthepieCollector


@pytest.fixture()
def sample_growthepie_data():
    return [
        {"origin_key": "mantle", "metric_key": "daa", "value": 42000, "date": "2026-03-13"},
        {"origin_key": "mantle", "metric_key": "txcount", "value": 150000, "date": "2026-03-13"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2_300_000_000, "date": "2026-03-13"},
        {"origin_key": "ethereum", "metric_key": "daa", "value": 500000, "date": "2026-03-13"},
    ]


def test_growthepie_collector_maps_daa_to_two_metrics(sample_growthepie_data):
    collector = GrowthepieCollector()
    records = collector._map_rows(sample_growthepie_data)

    mantle_records = [r for r in records if r.entity == "mantle"]
    names = {r.metric_name for r in mantle_records}
    assert "daily_active_users" in names
    assert "active_addresses" in names
    assert "chain_transactions" in names


def test_growthepie_collector_maps_values_correctly(sample_growthepie_data):
    collector = GrowthepieCollector()
    records = collector._map_rows(sample_growthepie_data)

    dau = next(r for r in records if r.metric_name == "daily_active_users")
    assert dau.value == Decimal("42000")

    txcount = next(r for r in records if r.metric_name == "chain_transactions")
    assert txcount.value == Decimal("150000")

    market_cap = next(r for r in records if r.metric_name == "mnt_market_cap")
    assert market_cap.value == Decimal("2300000000")


def test_growthepie_filters_only_mantle(sample_growthepie_data):
    collector = GrowthepieCollector()
    records = collector._map_rows(sample_growthepie_data)

    assert all(r.entity == "mantle" for r in records)


def test_growthepie_source_platform():
    collector = GrowthepieCollector()
    assert collector.source_platform == "growthepie"


def test_growthepie_uses_public_dot_com_base_url():
    collector = GrowthepieCollector()
    assert collector.BASE == "https://api.growthepie.com"


@pytest.mark.asyncio
async def test_growthepie_collect_uses_current_public_fundamentals_endpoint(sample_growthepie_data):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.growthepie.com/v1/fundamentals.json"
        return httpx.Response(200, json=sample_growthepie_data)

    collector = GrowthepieCollector(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    records = await collector.collect()

    assert {r.metric_name for r in records} == {
        "daily_active_users",
        "active_addresses",
        "chain_transactions",
        "mnt_market_cap",
    }
