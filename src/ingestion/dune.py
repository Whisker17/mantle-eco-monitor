from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from config.settings import Settings
from src.ingestion.base import BaseCollector, MetricRecord

logger = logging.getLogger(__name__)

METRIC_QUERY_MAP = {
    "stablecoin_transfer_volume": "dune_stablecoin_volume_query_id",
}

METRIC_UNITS = {
    "daily_active_users": "count",
    "active_addresses": "count",
    "chain_transactions": "count",
    "stablecoin_transfer_volume": "usd",
    "dex_volume": "usd",
}


class DuneClient:
    BASE_URL = "https://api.dune.com/api/v1"

    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self._http = http_client

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        return httpx.AsyncClient(
            headers={"X-Dune-API-Key": self.api_key},
            timeout=30.0,
        )

    async def get_latest_result(self, query_id: int) -> list[dict]:
        http = await self._get_http()
        resp = await http.get(f"{self.BASE_URL}/query/{query_id}/results")
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("rows", [])

    async def health_check(self) -> bool:
        try:
            http = await self._get_http()
            resp = await http.get(f"{self.BASE_URL}/query/1/results", params={"limit": 1})
            return 200 <= resp.status_code < 300
        except Exception:
            return False


class DuneCollector(BaseCollector):
    def __init__(self, client: DuneClient, settings: Settings | None = None):
        self._client = client
        self._settings = settings

    @property
    def source_platform(self) -> str:
        return "dune"

    def _map_rows(
        self,
        metric_name: str,
        rows: list[dict],
    ) -> list[MetricRecord]:
        records = []
        unit = METRIC_UNITS.get(metric_name, "count")
        for row in rows:
            day_raw = row.get("day") or row.get("date")
            if day_raw is None:
                continue
            if isinstance(day_raw, str):
                collected_at = datetime.fromisoformat(day_raw.replace("Z", "+00:00"))
                if collected_at.tzinfo is None:
                    collected_at = collected_at.replace(tzinfo=timezone.utc)
            else:
                collected_at = day_raw

            value = Decimal(str(row["value"]))
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name=metric_name,
                    value=value,
                    unit=unit,
                    source_platform="dune",
                    source_ref=None,
                    collected_at=collected_at,
                )
            )
        return records

    async def collect(self) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for metric_name, settings_attr in METRIC_QUERY_MAP.items():
            query_id = getattr(self._settings, settings_attr, 0) if self._settings else 0
            if not query_id:
                logger.warning("No query ID configured for %s, skipping", metric_name)
                continue
            try:
                rows = await self._client.get_latest_result(query_id)
                records.extend(self._map_rows(metric_name, rows))
            except Exception:
                logger.exception("Failed to collect %s from Dune", metric_name)
        return records

    async def health_check(self) -> bool:
        return await self._client.health_check()
