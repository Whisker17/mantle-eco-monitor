from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)


class AaveAdapter(ProtocolAdapter):
    SLUG = "aave-v3"
    DEFILLAMA_URL = "https://api.llama.fi/api/protocol/aave-v3"

    @property
    def slug(self) -> str:
        return self.SLUG

    @property
    def monitoring_tier(self) -> str:
        return "special"

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        resp = await http.get(self.DEFILLAMA_URL)
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data)

    def _parse(self, data: dict) -> list[MetricRecord]:
        chain_tvls = data.get("chainTvls", {})

        supply_entries = chain_tvls.get("Mantle", {}).get("tvl", [])
        borrow_entries = chain_tvls.get("Mantle-borrowed", {}).get("tvl", [])

        if not supply_entries:
            return []

        latest_supply = supply_entries[-1]
        supply = Decimal(str(latest_supply.get("totalLiquidityUSD", 0)))
        ts = datetime.fromtimestamp(latest_supply["date"], tz=timezone.utc)

        borrowed = Decimal("0")
        if borrow_entries:
            borrowed = Decimal(str(borrow_entries[-1].get("totalLiquidityUSD", 0)))

        utilization = borrowed / supply if supply > 0 else Decimal("0")
        tvl = supply - borrowed

        return [
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="supply",
                value=supply, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="borrowed",
                value=borrowed, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="utilization",
                value=utilization, unit="percent", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="tvl",
                value=tvl, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
        ]
