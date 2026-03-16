from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
        records = self._map_tvl_rows(data.get("chainTvls", {}).get("Mantle", {}).get("tvl", []))
        return records[-1:] if records else []

    async def collect_tvl_history(
        self,
        http: httpx.AsyncClient,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        resp = await http.get(f"https://api.llama.fi/protocol/{self._slug}")
        resp.raise_for_status()
        data = resp.json()
        records = self._map_tvl_rows(data.get("chainTvls", {}).get("Mantle", {}).get("tvl", []))
        anchor = today or datetime.now(tz=timezone.utc).date()
        cutoff = anchor - timedelta(days=max(days, 0))
        return [record for record in records if record.collected_at.date() >= cutoff]

    def _map_tvl_rows(self, rows: list[dict]) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for row in rows:
            timestamp = row.get("date")
            total_liquidity = row.get("totalLiquidityUSD")
            if timestamp is None or total_liquidity is None:
                continue
            records.append(
                MetricRecord(
                    scope="ecosystem",
                    entity=self._slug,
                    metric_name="tvl",
                    value=Decimal(str(total_liquidity)),
                    unit="usd",
                    source_platform="defillama",
                    source_ref=f"https://defillama.com/protocol/{self._slug}",
                    collected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
            )
        return records
