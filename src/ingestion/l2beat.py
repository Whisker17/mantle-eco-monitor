from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord

logger = logging.getLogger(__name__)


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

        latest = tvs_data[-1]
        timestamp = latest[0]
        total = Decimal(str(latest[1])) + Decimal(str(latest[2])) + Decimal(str(latest[3]))

        return [
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
        ]

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.BASE}{self.TVS_PATH}")
            return resp.status_code == 200
        except Exception:
            return False
