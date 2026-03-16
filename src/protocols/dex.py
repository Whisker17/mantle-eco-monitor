from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.ingestion.defillama import MANTLE_DEX_OVERVIEW_PATH, extract_mantle_dex_protocol_volume
from src.protocols.base import ProtocolAdapter

UNSAFE_MULTICHAIN_VOLUME_HISTORY_SLUGS = {"uniswap-v3", "woofi-swap"}


class DexAdapter(ProtocolAdapter):
    def __init__(self, protocol_slug: str):
        self._slug = protocol_slug

    @property
    def slug(self) -> str:
        return self._slug

    @property
    def monitoring_tier(self) -> str:
        return "dex"

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        records.extend(await self._collect_tvl(http))
        records.extend(await self._collect_volume(http))
        return records

    async def _collect_tvl(self, http: httpx.AsyncClient) -> list[MetricRecord]:
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
                scope="ecosystem", entity=self._slug, metric_name="tvl",
                value=Decimal(str(latest.get("totalLiquidityUSD", 0))),
                unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self._slug}",
                collected_at=datetime.fromtimestamp(latest["date"], tz=timezone.utc),
            )
        ]

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
        mantle_data = data.get("chainTvls", {}).get("Mantle", {}).get("tvl", [])
        records: list[MetricRecord] = []
        for row in mantle_data:
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
        return self._filter_records(records, days=days, today=today)

    async def _collect_volume(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        resp = await http.get(f"https://api.llama.fi{MANTLE_DEX_OVERVIEW_PATH}")
        resp.raise_for_status()
        data = resp.json()
        total_24h = extract_mantle_dex_protocol_volume(data, self._slug)
        if total_24h is None:
            return []
        return [
            MetricRecord(
                scope="ecosystem", entity=self._slug, metric_name="volume",
                value=Decimal(str(total_24h)),
                unit="usd", source_platform="defillama",
                source_ref=None,
                collected_at=datetime.now(tz=timezone.utc),
            )
        ]

    async def collect_volume_history(
        self,
        http: httpx.AsyncClient,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        if self._slug in UNSAFE_MULTICHAIN_VOLUME_HISTORY_SLUGS:
            return []

        resp = await http.get(f"https://api.llama.fi/summary/dexs/{self._slug}")
        resp.raise_for_status()
        data = resp.json()
        chart = data.get("totalDataChart", [])
        records: list[MetricRecord] = []
        for row in chart:
            if len(row) < 2:
                continue
            timestamp, value = row[0], row[1]
            records.append(
                MetricRecord(
                    scope="ecosystem",
                    entity=self._slug,
                    metric_name="volume",
                    value=Decimal(str(value)),
                    unit="usd",
                    source_platform="defillama",
                    source_ref=f"https://defillama.com/dexs/protocol/{self._slug}",
                    collected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
            )
        return self._filter_records(records, days=days, today=today)

    def _filter_records(
        self,
        records: list[MetricRecord],
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        anchor = today or datetime.now(tz=timezone.utc).date()
        cutoff = anchor - timedelta(days=max(days, 0))
        return [record for record in records if record.collected_at.date() >= cutoff]
