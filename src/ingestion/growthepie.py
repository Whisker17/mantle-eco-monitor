from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord

METRIC_KEY_MAP = {
    "txcount": [
        ("chain_transactions", "count"),
    ],
    "market_cap_usd": [
        ("mnt_market_cap", "usd"),
    ],
}


class GrowthepieCollector(BaseCollector):
    BASE = "https://api.growthepie.com"
    FUNDAMENTALS_PATH = "/v1/fundamentals.json"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def source_platform(self) -> str:
        return "growthepie"

    def _map_rows(self, data: list[dict]) -> list[MetricRecord]:
        mantle = [r for r in data if r.get("origin_key") == "mantle"]
        records: list[MetricRecord] = []
        for row in mantle:
            metric_key = row.get("metric_key")
            mappings = METRIC_KEY_MAP.get(metric_key, [])
            for metric_name, unit in mappings:
                value = row.get("value")
                if value is None:
                    continue
                date_str = row.get("date", "")
                if date_str:
                    collected_at = datetime.fromisoformat(date_str)
                    if collected_at.tzinfo is None:
                        collected_at = collected_at.replace(tzinfo=timezone.utc)
                else:
                    collected_at = datetime.now(tz=timezone.utc)

                records.append(
                    MetricRecord(
                        scope="core",
                        entity="mantle",
                        metric_name=metric_name,
                        value=Decimal(str(value)),
                        unit=unit,
                        source_platform="growthepie",
                        source_ref=None,
                        collected_at=collected_at,
                    )
                )
        return records

    def collect_history(
        self,
        data: list[dict],
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        records = self._map_rows(data)
        anchor = today or datetime.now(tz=timezone.utc).date()
        cutoff = anchor - timedelta(days=max(days, 0))
        return [record for record in records if record.collected_at.date() >= cutoff]

    async def collect_recent_history(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{self.FUNDAMENTALS_PATH}")
        resp.raise_for_status()
        data = resp.json()
        return self.collect_history(data, days=days, today=today)

    async def collect(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{self.FUNDAMENTALS_PATH}")
        resp.raise_for_status()
        data = resp.json()
        records = self._map_rows(data)
        if not records:
            return []
        latest_day = max(record.collected_at.date() for record in records)
        return [record for record in records if record.collected_at.date() == latest_day]

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.BASE}{self.FUNDAMENTALS_PATH}")
            return resp.status_code == 200
        except Exception:
            return False
