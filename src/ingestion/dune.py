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
    "stablecoin_transfer_tx_count": "count",
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


def _parse_dune_datetime(day_raw: str) -> datetime:
    normalized = day_raw.strip()
    if normalized.endswith(" UTC"):
        normalized = normalized.removesuffix(" UTC") + "+00:00"
        normalized = normalized.replace(" ", "T", 1)
    else:
        normalized = normalized.replace("Z", "+00:00")

    collected_at = datetime.fromisoformat(normalized)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)
    return collected_at


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
        if metric_name == "stablecoin_transfer_volume":
            return self._map_stablecoin_rows(rows)

        records = []
        unit = METRIC_UNITS.get(metric_name, "count")
        for row in rows:
            collected_at = self._parse_collected_at(row)
            if collected_at is None:
                continue

            value = Decimal(str(row["value"]))
            records.append(
                self._build_record(
                    entity="mantle",
                    metric_name=metric_name,
                    value=value,
                    unit=unit,
                    collected_at=collected_at,
                )
            )
        return records

    def _map_stablecoin_rows(self, rows: list[dict]) -> list[MetricRecord]:
        if not any("symbol" in row for row in rows):
            return self._map_single_metric_rows("stablecoin_transfer_volume", rows)

        records: list[MetricRecord] = []
        totals_by_day: dict[datetime, Decimal] = {}

        for row in rows:
            collected_at = self._parse_collected_at(row)
            symbol = row.get("symbol")
            if collected_at is None or not symbol:
                continue

            entity = f"mantle:{str(symbol).upper()}"
            volume = Decimal(str(row["volume"]))
            tx_count = Decimal(str(row["tx_count"]))

            records.append(
                self._build_record(
                    entity=entity,
                    metric_name="stablecoin_transfer_volume",
                    value=volume,
                    unit="usd",
                    collected_at=collected_at,
                )
            )
            records.append(
                self._build_record(
                    entity=entity,
                    metric_name="stablecoin_transfer_tx_count",
                    value=tx_count,
                    unit="count",
                    collected_at=collected_at,
                )
            )
            totals_by_day[collected_at] = totals_by_day.get(collected_at, Decimal("0")) + volume

        for collected_at, total_volume in sorted(totals_by_day.items(), reverse=True):
            records.append(
                self._build_record(
                    entity="mantle",
                    metric_name="stablecoin_transfer_volume",
                    value=total_volume,
                    unit="usd",
                    collected_at=collected_at,
                )
            )

        return records

    def _map_single_metric_rows(
        self,
        metric_name: str,
        rows: list[dict],
    ) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        unit = METRIC_UNITS.get(metric_name, "count")

        for row in rows:
            collected_at = self._parse_collected_at(row)
            if collected_at is None:
                continue

            records.append(
                self._build_record(
                    entity="mantle",
                    metric_name=metric_name,
                    value=Decimal(str(row["value"])),
                    unit=unit,
                    collected_at=collected_at,
                )
            )

        return records

    def _parse_collected_at(self, row: dict) -> datetime | None:
        day_raw = row.get("day") or row.get("date")
        if day_raw is None:
            return None
        if isinstance(day_raw, str):
            return _parse_dune_datetime(day_raw)
        return day_raw

    def _build_record(
        self,
        *,
        entity: str,
        metric_name: str,
        value: Decimal,
        unit: str,
        collected_at: datetime,
    ) -> MetricRecord:
        return MetricRecord(
            scope="core",
            entity=entity,
            metric_name=metric_name,
            value=value,
            unit=unit,
            source_platform="dune",
            source_ref=None,
            collected_at=collected_at,
        )

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
        query_id = getattr(self._settings, "dune_stablecoin_volume_query_id", 0) if self._settings else 0
        if query_id:
            try:
                await self._client.get_latest_result(query_id)
                return True
            except Exception:
                return False
        return await self._client.health_check()
