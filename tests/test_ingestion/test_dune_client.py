from decimal import Decimal

import httpx
import pytest

from src.ingestion.dune import DuneClient, DuneCollector, METRIC_QUERY_MAP


class FakeDuneClient(DuneClient):
    def __init__(self, results: dict[int, list[dict]]):
        super().__init__(api_key="fake")
        self._results = results

    async def get_query_result(
        self,
        query_id: int,
        *,
        params: dict[str, str] | None = None,
    ) -> list[dict]:
        return self._results.get(query_id, [])

    async def get_latest_result(self, query_id: int) -> list[dict]:
        return await self.get_query_result(query_id)

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


def test_dune_collector_maps_active_addresses_rows_to_metric_records(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="active_addresses",
        rows=[{"day": "2026-03-13", "value": 54321}],
    )

    assert len(records) == 1
    assert records[0].metric_name == "active_addresses"
    assert records[0].value == Decimal("54321")


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


def test_dune_collector_parses_utc_timestamp_strings(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="stablecoin_transfer_volume",
        rows=[{"day": "2026-03-14 00:00:00.000 UTC", "value": 123.45}],
    )

    assert len(records) == 1
    assert records[0].metric_name == "stablecoin_transfer_volume"
    assert records[0].unit == "usd"


def test_dune_collector_maps_stablecoin_breakdown_rows_to_token_and_aggregate_metrics(
    fake_dune_client,
):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="stablecoin_transfer_volume",
        rows=[
            {
                "day": "2026-03-14 00:00:00.000 UTC",
                "symbol": "USDT",
                "volume": 120.5,
                "tx_count": 7,
            },
            {
                "day": "2026-03-14 00:00:00.000 UTC",
                "symbol": "USDC",
                "volume": 30,
                "tx_count": 2,
            },
        ],
    )

    assert len(records) == 5

    by_key = {(record.entity, record.metric_name): record for record in records}

    assert by_key[("mantle:USDT", "stablecoin_transfer_volume")].value == Decimal("120.5")
    assert by_key[("mantle:USDT", "stablecoin_transfer_tx_count")].value == Decimal("7")
    assert by_key[("mantle:USDC", "stablecoin_transfer_volume")].value == Decimal("30")
    assert by_key[("mantle:USDC", "stablecoin_transfer_tx_count")].value == Decimal("2")
    assert by_key[("mantle", "stablecoin_transfer_volume")].value == Decimal("150.5")


def test_dune_collector_source_platform(fake_dune_client):
    collector = DuneCollector(fake_dune_client)
    assert collector.source_platform == "dune"


@pytest.mark.asyncio
async def test_dune_collector_health_check(fake_dune_client):
    collector = DuneCollector(fake_dune_client)
    assert await collector.health_check() is True


@pytest.mark.asyncio
async def test_dune_collector_health_check_uses_configured_query():
    class ProbeDuneClient(FakeDuneClient):
        def __init__(self):
            super().__init__(
                results={
                    42: [
                        {
                            "day": "2026-03-13",
                            "symbol": "USDT",
                            "volume": 123.45,
                            "tx_count": 10,
                        }
                    ]
                }
            )
            self.health_check_calls = 0
            self.query_ids: list[int] = []

        async def get_query_result(
            self,
            query_id: int,
            *,
            params: dict[str, str] | None = None,
        ) -> list[dict]:
            self.query_ids.append(query_id)
            return await super().get_query_result(query_id, params=params)

        async def health_check(self) -> bool:
            self.health_check_calls += 1
            return False

    class FakeSettings:
        dune_stablecoin_volume_query_id = 42

    client = ProbeDuneClient()
    collector = DuneCollector(client, FakeSettings())

    assert await collector.health_check() is True
    assert client.query_ids == [42]
    assert client.health_check_calls == 0


def test_dune_metric_query_map_keeps_only_uncovered_metrics():
    assert METRIC_QUERY_MAP == {
        "daily_active_users": "dune_daily_active_users_query_id",
        "active_addresses": "dune_active_addresses_query_id",
        "chain_transactions": "dune_chain_transactions_query_id",
        "stablecoin_transfer_volume": "dune_stablecoin_volume_query_id",
    }


@pytest.mark.asyncio
async def test_dune_client_executes_parameterized_query_and_fetches_result():
    seen_requests: list[tuple[str, str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/query/42/execute":
            seen_requests.append((request.method, request.url.path, request.read().decode()))
            return httpx.Response(200, json={"execution_id": "exec-42", "state": "QUERY_STATE_PENDING"})
        if request.method == "GET" and request.url.path == "/api/v1/execution/exec-42/status":
            seen_requests.append((request.method, request.url.path, None))
            return httpx.Response(
                200,
                json={"execution_id": "exec-42", "state": "QUERY_STATE_COMPLETED", "is_execution_finished": True},
            )
        if request.method == "GET" and request.url.path == "/api/v1/execution/exec-42/results":
            seen_requests.append((request.method, request.url.path, None))
            return httpx.Response(200, json={"result": {"rows": [{"day": "2026-03-01", "value": 1}]}})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = DuneClient(
        api_key="token",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=30.0),
    )

    rows = await client.get_query_result(
        42,
        params={"start_date": "2026-03-01", "end_date": "2026-03-05"},
    )

    assert rows == [{"day": "2026-03-01", "value": 1}]
    assert seen_requests == [
        ("POST", "/api/v1/query/42/execute", '{"query_parameters":{"start_date":"2026-03-01","end_date":"2026-03-05"},"performance":"medium"}'),
        ("GET", "/api/v1/execution/exec-42/status", None),
        ("GET", "/api/v1/execution/exec-42/results", None),
    ]


@pytest.mark.asyncio
async def test_dune_client_health_check_requires_success_status():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = DuneClient(
        api_key="missing",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_dune_collector_collects_stablecoin_transfer_volume_when_configured():
    client = FakeDuneClient(
        results={
            42: [
                {
                    "day": "2026-03-13",
                    "symbol": "USDT",
                    "volume": 1234567.89,
                    "tx_count": 321,
                },
            ]
        }
    )

    class FakeSettings:
        dune_stablecoin_volume_query_id = 42

    collector = DuneCollector(client, FakeSettings())

    records = await collector.collect()

    assert len(records) == 3

    by_key = {(record.entity, record.metric_name): record for record in records}

    assert by_key[("mantle:USDT", "stablecoin_transfer_volume")].value == Decimal("1234567.89")
    assert by_key[("mantle:USDT", "stablecoin_transfer_tx_count")].value == Decimal("321")
    assert by_key[("mantle", "stablecoin_transfer_volume")].value == Decimal("1234567.89")


@pytest.mark.asyncio
async def test_dune_collector_skips_stablecoin_transfer_volume_when_query_id_missing():
    client = FakeDuneClient(results={})

    class FakeSettings:
        dune_stablecoin_volume_query_id = 0

    collector = DuneCollector(client, FakeSettings())

    records = await collector.collect()

    assert records == []
