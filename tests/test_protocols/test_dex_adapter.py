from decimal import Decimal

import httpx
import pytest

from src.protocols.dex import DexAdapter


@pytest.mark.asyncio
async def test_dex_adapter_uses_current_defillama_protocol_path():
    protocol_payload = {
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 12_500_000}],
            },
        }
    }
    volume_payload = {
        "protocols": [
            {
                "displayName": "Merchant Moe DEX",
                "module": "merchant-moe",
                "slug": "merchant-moe-dex",
                "total24h": 8_250_000,
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/protocol/merchant-moe-dex":
            return httpx.Response(200, json=protocol_payload)
        if request.url.path == "/overview/dexs/Mantle":
            return httpx.Response(200, json=volume_payload)
        return httpx.Response(404, json={})

    adapter = DexAdapter("merchant-moe-dex")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    records = await adapter.collect(http)

    names = {record.metric_name: record for record in records}
    assert names["tvl"].value == Decimal("12500000")
    assert names["volume"].value == Decimal("8250000")


@pytest.mark.asyncio
async def test_dex_adapter_uses_mantle_chain_volume_for_multichain_dex():
    protocol_payload = {
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 12_500_000}],
            },
        }
    }
    overview_payload = {
        "protocols": [
            {
                "displayName": "Uniswap V3",
                "module": "uniswap-v3",
                "slug": "uniswap-v3",
                "total24h": 42_932,
            }
        ]
    }
    summary_payload = {"total24h": 492_677_436}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/protocol/uniswap-v3":
            return httpx.Response(200, json=protocol_payload)
        if request.url.path == "/overview/dexs/Mantle":
            return httpx.Response(200, json=overview_payload)
        if request.url.path == "/summary/dexs/uniswap-v3":
            return httpx.Response(200, json=summary_payload)
        return httpx.Response(404, json={})

    adapter = DexAdapter("uniswap-v3")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    records = await adapter.collect(http)

    names = {record.metric_name: record for record in records}
    assert names["volume"].value == Decimal("42932")


@pytest.mark.asyncio
async def test_dex_adapter_keeps_tvl_when_volume_endpoint_is_missing():
    protocol_payload = {
        "chainTvls": {
            "Mantle": {
                "tvl": [{"date": 1710374400, "totalLiquidityUSD": 12_500_000}],
            },
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/protocol/mantle-index-four-fund":
            return httpx.Response(200, json=protocol_payload)
        if request.url.path == "/overview/dexs/Mantle":
            return httpx.Response(200, json={"protocols": []})
        return httpx.Response(404, json={})

    adapter = DexAdapter("mantle-index-four-fund")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    records = await adapter.collect(http)

    assert len(records) == 1
    assert records[0].metric_name == "tvl"
    assert records[0].value == Decimal("12500000")
