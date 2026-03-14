from decimal import Decimal

import pytest

from src.ingestion.dune import DuneClient, DuneCollector, METRIC_QUERY_MAP


class FakeDuneClient(DuneClient):
    def __init__(self, results: dict[int, list[dict]]):
        super().__init__(api_key="fake")
        self._results = results

    async def get_latest_result(self, query_id: int) -> list[dict]:
        return self._results.get(query_id, [])

    async def health_check(self) -> bool:
        return True


@pytest.fixture()
def fake_dune_client():
    return FakeDuneClient(results={})


def test_dune_collector_maps_query_rows_to_metric_records(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="daily_active_users",
        rows=[{"day": "2026-03-13", "value": 12345}],
    )

    assert len(records) == 1
    assert records[0].metric_name == "daily_active_users"
    assert records[0].value == Decimal("12345")
    assert records[0].scope == "core"
    assert records[0].entity == "mantle"
    assert records[0].unit == "count"
    assert records[0].source_platform == "dune"


def test_dune_collector_maps_multiple_rows(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="dex_volume",
        rows=[
            {"day": "2026-03-13", "value": 5000000},
            {"day": "2026-03-12", "value": 4500000},
        ],
    )

    assert len(records) == 2
    assert records[0].value == Decimal("5000000")
    assert records[1].value == Decimal("4500000")
    assert records[0].unit == "usd"


def test_dune_collector_skips_rows_without_day(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="chain_transactions",
        rows=[{"value": 999}],
    )

    assert len(records) == 0


def test_dune_collector_source_platform(fake_dune_client):
    collector = DuneCollector(fake_dune_client)
    assert collector.source_platform == "dune"


@pytest.mark.asyncio
async def test_dune_collector_health_check(fake_dune_client):
    collector = DuneCollector(fake_dune_client)
    assert await collector.health_check() is True


def test_dune_metric_query_map_keeps_only_uncovered_metrics():
    assert METRIC_QUERY_MAP == {
        "stablecoin_transfer_volume": "dune_stablecoin_volume_query_id",
    }
