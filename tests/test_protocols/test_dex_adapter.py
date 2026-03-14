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
    volume_payload = {"total24h": 8_250_000}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/protocol/merchant-moe-dex":
            return httpx.Response(200, json=protocol_payload)
        if request.url.path == "/summary/dexs/merchant-moe-dex":
            return httpx.Response(200, json=volume_payload)
        return httpx.Response(404, json={})

    adapter = DexAdapter("merchant-moe-dex")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    records = await adapter.collect(http)

    names = {record.metric_name: record for record in records}
    assert names["tvl"].value == Decimal("12500000")
    assert names["volume"].value == Decimal("8250000")
