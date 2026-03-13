from decimal import Decimal

import pytest

from src.ingestion.growthepie import GrowthepieCollector


@pytest.fixture()
def sample_growthepie_data():
    return [
        {"origin_key": "mantle", "metric_key": "daa", "value": 42000, "date": "2026-03-13"},
        {"origin_key": "mantle", "metric_key": "txcount", "value": 150000, "date": "2026-03-13"},
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


def test_growthepie_filters_only_mantle(sample_growthepie_data):
    collector = GrowthepieCollector()
    records = collector._map_rows(sample_growthepie_data)

    assert all(r.entity == "mantle" for r in records)


def test_growthepie_source_platform():
    collector = GrowthepieCollector()
    assert collector.source_platform == "growthepie"
