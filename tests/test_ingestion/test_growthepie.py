from datetime import date
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
    assert "chain_transactions" in names
    assert "daily_active_users" not in names
    assert "active_addresses" not in names


def test_growthepie_collector_maps_values_correctly(sample_growthepie_data):
    collector = GrowthepieCollector()
    records = collector._map_rows(sample_growthepie_data)

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
        "chain_transactions",
        "mnt_market_cap",
    }


@pytest.mark.asyncio
async def test_growthepie_collect_returns_only_latest_mantle_day():
    payload = [
        {"origin_key": "mantle", "metric_key": "txcount", "value": 100000, "date": "2026-03-15"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2200000000, "date": "2026-03-15"},
        {"origin_key": "mantle", "metric_key": "txcount", "value": 150000, "date": "2026-03-16"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2300000000, "date": "2026-03-16"},
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    collector = GrowthepieCollector(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    records = await collector.collect()

    assert len(records) == 2
    assert {record.metric_name: record.value for record in records} == {
        "chain_transactions": Decimal("150000"),
        "mnt_market_cap": Decimal("2300000000"),
    }


def test_growthepie_collect_history_filters_to_recent_90_day_window():
    payload = [
        {"origin_key": "mantle", "metric_key": "txcount", "value": 100000, "date": "2025-01-01"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2100000000, "date": "2025-01-01"},
        {"origin_key": "mantle", "metric_key": "txcount", "value": 120000, "date": "2025-03-10"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2200000000, "date": "2025-03-10"},
        {"origin_key": "mantle", "metric_key": "txcount", "value": 150000, "date": "2025-06-03"},
        {"origin_key": "mantle", "metric_key": "market_cap_usd", "value": 2300000000, "date": "2025-06-03"},
    ]

    collector = GrowthepieCollector()

    records = collector.collect_history(payload, days=90, today=date(2025, 6, 3))

    assert len(records) == 4
    assert {(record.metric_name, str(record.value)) for record in records} == {
        ("chain_transactions", "120000"),
        ("mnt_market_cap", "2200000000"),
        ("chain_transactions", "150000"),
        ("mnt_market_cap", "2300000000"),
    }
