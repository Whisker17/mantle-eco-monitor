from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord

logger = logging.getLogger(__name__)


class CoinGeckoCollector(BaseCollector):
    BASE = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        api_key: str = "",
        http_client: httpx.AsyncClient | None = None,
    ):
        headers = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        self._http = http_client or httpx.AsyncClient(timeout=30.0, headers=headers)

    @property
    def source_platform(self) -> str:
        return "coingecko"

    async def collect(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}/coins/mantle")
        resp.raise_for_status()
        data = resp.json()
        market = data.get("market_data", {})
        now = datetime.now(tz=timezone.utc)
        records: list[MetricRecord] = []

        volume = market.get("total_volume", {}).get("usd")
        if volume is not None:
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name="mnt_volume",
                    value=Decimal(str(volume)),
                    unit="usd",
                    source_platform="coingecko",
                    source_ref="https://www.coingecko.com/en/coins/mantle",
                    collected_at=now,
                )
            )

        return records

    async def collect_mnt_volume_history(self) -> list[MetricRecord]:
        resp = await self._http.get(
            f"{self.BASE}/coins/mantle/market_chart",
            params={
                "vs_currency": "usd",
                "days": "max",
                "interval": "daily",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return self._map_volume_history(data.get("total_volumes", []))

    def _map_volume_history(self, rows: list[list[float | int]]) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for row in rows:
            if len(row) < 2:
                continue
            timestamp_ms, volume = row[0], row[1]
            if volume is None:
                continue
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name="mnt_volume",
                    value=Decimal(str(volume)),
                    unit="usd",
                    source_platform="coingecko",
                    source_ref="https://www.coingecko.com/en/coins/mantle",
                    collected_at=datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc),
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.BASE}/ping")
            return resp.status_code == 200
        except Exception:
            return False
