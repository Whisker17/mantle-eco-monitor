from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.ingestion.defillama import MANTLE_DEX_OVERVIEW_PATH, extract_mantle_dex_protocol_volume
from src.protocols.dex import UNSAFE_MULTICHAIN_VOLUME_HISTORY_SLUGS
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

    async def collect_tvl_history(
        self,
        http: httpx.AsyncClient,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        per_slug: dict[str, dict[date, Decimal]] = {}
        for child_slug in self._tvl_slugs:
            resp = await http.get(f"https://api.llama.fi/protocol/{child_slug}")
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("chainTvls", {}).get("Mantle", {}).get("tvl", [])
            per_slug[child_slug] = {
                datetime.fromtimestamp(row["date"], tz=timezone.utc).date(): Decimal(
                    str(row.get("totalLiquidityUSD", 0))
                )
                for row in rows
                if row.get("date") is not None
            }

        all_days = sorted({day for slug_rows in per_slug.values() for day in slug_rows})
        records: list[MetricRecord] = []
        for day in all_days:
            total_tvl = sum((slug_rows.get(day, Decimal("0")) for slug_rows in per_slug.values()), Decimal("0"))
            records.append(
                MetricRecord(
                    scope="ecosystem",
                    entity=self._slug,
                    metric_name="tvl",
                    value=total_tvl,
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com",
                    collected_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                )
            )
        return self._filter_records(records, days=days, today=today)

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

    async def collect_volume_history(
        self,
        http: httpx.AsyncClient,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        if not self._volume_slugs or any(slug in UNSAFE_MULTICHAIN_VOLUME_HISTORY_SLUGS for slug in self._volume_slugs):
            return []

        per_slug: dict[str, dict[date, Decimal]] = {}
        for child_slug in self._volume_slugs:
            resp = await http.get(f"https://api.llama.fi/summary/dexs/{child_slug}")
            resp.raise_for_status()
            data = resp.json()
            chart = data.get("totalDataChart", [])
            per_slug[child_slug] = {
                datetime.fromtimestamp(row[0], tz=timezone.utc).date(): Decimal(str(row[1]))
                for row in chart
                if len(row) >= 2
            }

        all_days = sorted({day for slug_rows in per_slug.values() for day in slug_rows})
        records: list[MetricRecord] = []
        for day in all_days:
            total_volume = sum((slug_rows.get(day, Decimal("0")) for slug_rows in per_slug.values()), Decimal("0"))
            records.append(
                MetricRecord(
                    scope="ecosystem",
                    entity=self._slug,
                    metric_name="volume",
                    value=total_volume,
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com",
                    collected_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
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
