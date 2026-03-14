from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.protocols.base import ProtocolAdapter


class GenericAdapter(ProtocolAdapter):
    def __init__(self, protocol_slug: str):
        self._slug = protocol_slug

    @property
    def slug(self) -> str:
        return self._slug

    @property
    def monitoring_tier(self) -> str:
        return "generic"

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        resp = await http.get(f"https://api.llama.fi/protocol/{self._slug}")
        resp.raise_for_status()
        data = resp.json()
        chain_tvls = data.get("chainTvls", {})
        mantle_data = chain_tvls.get("Mantle", {}).get("tvl", [])
        if not mantle_data:
            return []

        latest = mantle_data[-1]
        return [
            MetricRecord(
                scope="ecosystem",
                entity=self._slug,
                metric_name="tvl",
                value=Decimal(str(latest.get("totalLiquidityUSD", 0))),
                unit="usd",
                source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self._slug}",
                collected_at=datetime.fromtimestamp(latest["date"], tz=timezone.utc),
            )
        ]
