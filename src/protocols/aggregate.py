from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.ingestion.defillama import MANTLE_DEX_OVERVIEW_PATH, extract_mantle_dex_protocol_volume
from src.protocols.base import ProtocolAdapter


class AggregateAdapter(ProtocolAdapter):
    def __init__(
        self,
        *,
        slug: str,
        monitoring_tier: str,
        tvl_slugs: list[str],
        volume_slugs: list[str] | None = None,
    ):
        self._slug = slug
        self._tier = monitoring_tier
        self._tvl_slugs = tvl_slugs
        self._volume_slugs = volume_slugs or []

    @property
    def slug(self) -> str:
        return self._slug

    @property
    def monitoring_tier(self) -> str:
        return self._tier

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        tvl_records = await self._collect_tvl(http)
        if tvl_records:
            records.extend(tvl_records)
        volume_records = await self._collect_volume(http)
        if volume_records:
            records.extend(volume_records)
        return records

    async def _collect_tvl(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        total_tvl = Decimal("0")
        latest_at: datetime | None = None

        for child_slug in self._tvl_slugs:
            resp = await http.get(f"https://api.llama.fi/protocol/{child_slug}")
            resp.raise_for_status()
            data = resp.json()
            mantle_data = data.get("chainTvls", {}).get("Mantle", {}).get("tvl", [])
            if not mantle_data:
                continue

            latest = mantle_data[-1]
            total_tvl += Decimal(str(latest.get("totalLiquidityUSD", 0)))
            collected_at = datetime.fromtimestamp(latest["date"], tz=timezone.utc)
            latest_at = collected_at if latest_at is None else max(latest_at, collected_at)

        if latest_at is None:
            return []

        return [
            MetricRecord(
                scope="ecosystem",
                entity=self._slug,
                metric_name="tvl",
                value=total_tvl,
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com",
                collected_at=latest_at,
            )
        ]

    async def _collect_volume(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        if not self._volume_slugs:
            return []

        resp = await http.get(f"https://api.llama.fi{MANTLE_DEX_OVERVIEW_PATH}")
        resp.raise_for_status()
        data = resp.json()

        total_24h = Decimal("0")
        matched = False
        for child_slug in self._volume_slugs:
            volume = extract_mantle_dex_protocol_volume(data, child_slug)
            if volume is None:
                continue
            total_24h += Decimal(str(volume))
            matched = True

        if not matched:
            return []

        return [
            MetricRecord(
                scope="ecosystem",
                entity=self._slug,
                metric_name="volume",
                value=total_24h,
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com",
                collected_at=datetime.now(tz=timezone.utc),
            )
        ]
