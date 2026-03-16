from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.protocols.aave import AaveAdapter


@pytest.fixture()
def sample_aave_payload():
    return {
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 245_000_000}],
            },
            "Mantle-borrowed": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 89_000_000}],
            },
        }
    }


def test_aave_adapter_returns_supply_borrowed_utilization(sample_aave_payload):
    adapter = AaveAdapter()
    records = adapter._parse(sample_aave_payload)

    assert len(records) == 4
    names = {r.metric_name: r for r in records}

    assert names["supply"].value == Decimal("245000000")
    assert names["borrowed"].value == Decimal("89000000")
    assert names["tvl"].value == Decimal("245000000")

    utilization = names["utilization"].value
    expected = Decimal("89000000") / Decimal("245000000")
    assert abs(utilization - expected) < Decimal("0.0001")


def test_aave_adapter_all_records_are_ecosystem_scope(sample_aave_payload):
    adapter = AaveAdapter()
    records = adapter._parse(sample_aave_payload)

    assert all(r.scope == "ecosystem" for r in records)
    assert all(r.entity == "aave-v3" for r in records)


def test_aave_adapter_handles_missing_borrowed():
    data = {
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 100_000_000}],
            },
        }
    }
    adapter = AaveAdapter()
    records = adapter._parse(data)

    names = {r.metric_name: r for r in records}
    assert names["borrowed"].value == Decimal("0")
    assert names["utilization"].value == Decimal("0")
    assert names["tvl"].value == Decimal("100000000")


def test_aave_adapter_keeps_tvl_non_negative_when_borrowed_exceeds_supply():
    data = {
        "tvl": [{"date": 1710374400, "totalLiquidityUSD": 487_233_030}],
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 487_233_030}],
            },
            "Mantle-borrowed": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 520_163_019}],
            },
        },
    }

    adapter = AaveAdapter()
    records = adapter._parse(data)

    names = {r.metric_name: r for r in records}
    assert names["tvl"].value == Decimal("487233030")


def test_aave_adapter_slug_and_tier():
    adapter = AaveAdapter()
    assert adapter.slug == "aave-v3"
    assert adapter.monitoring_tier == "special"


def test_aave_adapter_uses_current_defillama_protocol_path():
    assert AaveAdapter.DEFILLAMA_URL == "https://api.llama.fi/protocol/aave-v3"


@pytest.mark.asyncio
async def test_aave_adapter_collect_history_maps_recent_series():
    payload = {
        "chainTvls": {
            "Mantle": {
                "tvl": [
                    {"date": 1741564800, "totalLiquidityUSD": 200_000_000},  # 2025-03-10
                    {"date": 1748908800, "totalLiquidityUSD": 245_000_000},  # 2025-06-03
                ],
            },
            "Mantle-borrowed": {
                "tvl": [
                    {"date": 1741564800, "totalLiquidityUSD": 70_000_000},
                    {"date": 1748908800, "totalLiquidityUSD": 89_000_000},
                ],
            },
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = AaveAdapter()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    records = await adapter.collect_history(http, days=90, today=date(2025, 6, 3))

    assert len(records) == 8
    by_key = {(record.metric_name, record.collected_at.date().isoformat()): record for record in records}
    assert by_key[("tvl", "2025-03-10")].value == Decimal("200000000")
    assert by_key[("supply", "2025-06-03")].value == Decimal("245000000")
    assert by_key[("borrowed", "2025-06-03")].value == Decimal("89000000")
