from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord


class L2BeatCollector(BaseCollector):
    BASE = "https://l2beat.com/api"
    TVS_PATH = "/scaling/tvs/mantle"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def source_platform(self) -> str:
        return "l2beat"

    async def collect(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{self.TVS_PATH}")
        resp.raise_for_status()
        data = resp.json()

        tvs_data = data.get("data", {}).get("chart", {}).get("data", [])
        if not tvs_data:
            return []

        return self._map_tvs_rows(tvs_data[-1:])

    async def collect_total_value_secured_history(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{self.TVS_PATH}")
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("chart", {}).get("data", [])
        return self._filter_records_by_window(
            self._map_tvs_rows(rows),
            days=days,
            today=today,
        )

    def _map_tvs_rows(self, rows: list[list[float | int]]) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for row in rows:
            if len(row) < 4:
                continue
            timestamp = row[0]
            total = Decimal(str(row[1])) + Decimal(str(row[2])) + Decimal(str(row[3]))
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name="total_value_secured",
                    value=total,
                    unit="usd",
                    source_platform="l2beat",
                    source_ref="https://l2beat.com/scaling/projects/mantle",
                    collected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
            )
        return records

    def _filter_records_by_window(
        self,
        records: list[MetricRecord],
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        anchor = today or datetime.now(tz=timezone.utc).date()
        cutoff = anchor - timedelta(days=max(days, 0))
        return [record for record in records if record.collected_at.date() >= cutoff]

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.BASE}{self.TVS_PATH}")
            return resp.status_code == 200
        except Exception:
            return False
