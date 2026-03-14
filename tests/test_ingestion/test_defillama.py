from decimal import Decimal

import httpx
import pytest

from src.ingestion.defillama import DefiLlamaCollector


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: dict[str, dict]):
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for key, resp in self._responses.items():
            if key in str(request.url):
                return httpx.Response(200, json=resp)
        return httpx.Response(404, json={})


@pytest.fixture()
def sample_defillama_tvl_payload():
    return [
        {"date": 1710288000, "tvl": 1_523_000_000},
        {"date": 1710374400, "tvl": 1_600_000_000},
    ]


@pytest.fixture()
def sample_defillama_stablecoin_payload():
    return [
        {
            "date": 1710374400,
            "totalCirculatingUSD": {"peggedUSD": 500_000_000},
        }
    ]


@pytest.fixture()
def sample_defillama_stablecoin_chains_payload():
    return [
        {"name": "Ethereum", "totalCirculatingUSD": {"peggedUSD": 50_000_000_000}},
        {"name": "Mantle", "totalCirculatingUSD": {"peggedUSD": 500_000_000}},
    ]


@pytest.fixture()
def sample_defillama_dex_overview_payload():
    return {
        "chain": "Mantle",
        "total24h": 32_000_000,
        "totalDataChart": [
            [1710288000, 28_000_000],
            [1710374400, 32_000_000],
        ],
    }


@pytest.fixture()
def defillama_collector(
    sample_defillama_tvl_payload,
    sample_defillama_stablecoin_payload,
    sample_defillama_stablecoin_chains_payload,
    sample_defillama_dex_overview_payload,
):
    transport = FakeTransport(
        {
            "historicalChainTvl/Mantle": sample_defillama_tvl_payload,
            "stablecoincharts/Mantle": sample_defillama_stablecoin_payload,
            "stablecoinchains": sample_defillama_stablecoin_chains_payload,
            "overview/dexs/Mantle": sample_defillama_dex_overview_payload,
        }
    )
    client = httpx.AsyncClient(transport=transport)
    return DefiLlamaCollector(http_client=client)


@pytest.mark.asyncio
async def test_defillama_collector_maps_chain_tvl(defillama_collector):
    records = await defillama_collector._collect_chain_tvl()

    assert len(records) == 1
    assert records[0].metric_name == "tvl"
    assert records[0].value == Decimal("1600000000")
    assert records[0].entity == "mantle"
    assert records[0].scope == "core"


@pytest.mark.asyncio
async def test_defillama_collector_maps_stablecoin_supply(defillama_collector):
    records = await defillama_collector._collect_stablecoin_supply()

    assert len(records) == 1
    assert records[0].metric_name == "stablecoin_supply"
    assert records[0].value == Decimal("500000000")


@pytest.mark.asyncio
async def test_defillama_collector_maps_stablecoin_mcap(defillama_collector):
    records = await defillama_collector._collect_stablecoin_mcap()

    assert len(records) == 1
    assert records[0].metric_name == "stablecoin_mcap"
    assert records[0].value == Decimal("500000000")


@pytest.mark.asyncio
async def test_defillama_collect_returns_all_core_metrics(defillama_collector):
    records = await defillama_collector.collect()

    names = {r.metric_name for r in records}
    assert "tvl" in names
    assert "stablecoin_supply" in names
    assert "stablecoin_mcap" in names
    assert "dex_volume" in names


def test_defillama_source_platform():
    collector = DefiLlamaCollector()
    assert collector.source_platform == "defillama"
