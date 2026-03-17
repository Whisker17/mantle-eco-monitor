from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord

MANTLE_DEX_OVERVIEW_PATH = "/overview/dexs/Mantle"


def extract_mantle_dex_protocol_volume(payload: dict, slug: str) -> Decimal | None:
    protocols = payload.get("protocols", [])
    for protocol in protocols:
        if protocol.get("slug") != slug and protocol.get("module") != slug:
            continue
        total_24h = protocol.get("total24h")
        if total_24h is None:
            return None
        return Decimal(str(total_24h))
    return None


class DefiLlamaCollector(BaseCollector):
    BASE = "https://api.llama.fi"
    STABLES_BASE = "https://stablecoins.llama.fi"
    PROTOCOL_PATH = "/protocol"

    METRIC_GROUPS = frozenset({"tvl", "stablecoin", "dex"})

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        metrics: list[str] | None = None,
    ):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self._metrics = metrics

    @property
    def source_platform(self) -> str:
        return "defillama"

    def _should_collect(self, group: str) -> bool:
        return self._metrics is None or group in self._metrics

    async def collect(self) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        if self._should_collect("tvl"):
            records.extend(await self._collect_chain_tvl())
        if self._should_collect("stablecoin"):
            records.extend(await self._collect_stablecoin_supply())
            records.extend(await self._collect_stablecoin_mcap())
        if self._should_collect("dex"):
            records.extend(await self._collect_chain_dex_volume())
        return records

    async def _collect_chain_tvl(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}/v2/historicalChainTvl/Mantle")
        resp.raise_for_status()
        data = resp.json()
        return self._map_chain_tvl_rows(data[-1:] if data else [])

    async def collect_chain_tvl_history(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}/v2/historicalChainTvl/Mantle")
        resp.raise_for_status()
        data = resp.json()
        return self._map_chain_tvl_rows(data)

    def _map_chain_tvl_rows(self, rows: list[dict]) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for row in rows:
            tvl = row.get("tvl")
            timestamp = row.get("date")
            if tvl is None or timestamp is None:
                continue
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name="tvl",
                    value=Decimal(str(tvl)),
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/chain/Mantle",
                    collected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
            )
        return records

    async def collect_stablecoin_supply_history(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        return await self._map_stablecoin_history(
            metric_name="stablecoin_supply",
            days=days,
            today=today,
        )

    async def collect_stablecoin_mcap_history(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        return await self._map_stablecoin_history(
            metric_name="stablecoin_mcap",
            days=days,
            today=today,
        )

    async def _fetch_stablecoin_chart_rows(self) -> list[dict]:
        resp = await self._http.get(f"{self.STABLES_BASE}/stablecoincharts/Mantle")
        resp.raise_for_status()
        return resp.json()

    async def _map_stablecoin_history(
        self,
        *,
        metric_name: str,
        days: int,
        today: date | None,
    ) -> list[MetricRecord]:
        data = await self._fetch_stablecoin_chart_rows()
        records: list[MetricRecord] = []
        for row in data:
            timestamp = row.get("date")
            total = row.get("totalCirculatingUSD", {}).get("peggedUSD")
            if timestamp is None or total is None:
                continue
            records.append(
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name=metric_name,
                    value=Decimal(str(total)),
                    unit="usd",
                    source_platform="defillama",
                    source_ref=None,
                    collected_at=datetime.fromtimestamp(int(timestamp), tz=timezone.utc),
                )
            )
        return self._filter_records_by_window(records, days=days, today=today)

    async def _collect_stablecoin_supply(self) -> list[MetricRecord]:
        data = await self._fetch_stablecoin_chart_rows()
        if not data:
            return []
        latest = data[-1]
        total = Decimal(str(latest.get("totalCirculatingUSD", {}).get("peggedUSD", 0)))
        return [
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="stablecoin_supply",
                value=total,
                unit="usd",
                source_platform="defillama",
                source_ref=None,
                collected_at=datetime.fromtimestamp(int(latest["date"]), tz=timezone.utc),
            )
        ]

    async def _collect_chain_dex_volume(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{MANTLE_DEX_OVERVIEW_PATH}")
        resp.raise_for_status()
        data = resp.json()
        chart = data.get("totalDataChart", [])
        if chart:
            timestamp, value = chart[-1]
            collected_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            value = data.get("total24h")
            if value is None:
                return []
            collected_at = datetime.now(tz=timezone.utc)

        return [
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="dex_volume",
                value=Decimal(str(value)),
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com/chain/Mantle?flows=false&dexs=true",
                collected_at=collected_at,
            )
        ]

    async def collect_chain_dex_volume_history(
        self,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{MANTLE_DEX_OVERVIEW_PATH}")
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
                    scope="core",
                    entity="mantle",
                    metric_name="dex_volume",
                    value=Decimal(str(value)),
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/chain/Mantle?flows=false&dexs=true",
                    collected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                )
            )
        return self._filter_records_by_window(records, days=days, today=today)

    async def _collect_stablecoin_mcap(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.STABLES_BASE}/stablecoinchains")
        resp.raise_for_status()
        data = resp.json()
        for chain in data:
            if chain.get("name", "").lower() == "mantle":
                return [
                    MetricRecord(
                        scope="core",
                        entity="mantle",
                        metric_name="stablecoin_mcap",
                        value=Decimal(str(chain.get("totalCirculatingUSD", {}).get("peggedUSD", 0))),
                        unit="usd",
                        source_platform="defillama",
                        source_ref=None,
                        collected_at=datetime.now(tz=timezone.utc),
                    )
                ]
        return []

    async def collect_protocol_tvl(self, slug: str) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{self.PROTOCOL_PATH}/{slug}")
        resp.raise_for_status()
        data = resp.json()
        chain_tvls = data.get("chainTvls", {})
        mantle_data = chain_tvls.get("Mantle", {}).get("tvl", [])
        if not mantle_data:
            return []
        latest = mantle_data[-1]
        return [
            MetricRecord(
                scope="ecosystem",
                entity=slug,
                metric_name="tvl",
                value=Decimal(str(latest.get("totalLiquidityUSD", 0))),
                unit="usd",
                source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{slug}",
                collected_at=datetime.fromtimestamp(latest["date"], tz=timezone.utc),
            )
        ]

    async def collect_dex_volume(self, slug: str) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}{MANTLE_DEX_OVERVIEW_PATH}")
        resp.raise_for_status()
        data = resp.json()
        total_24h = extract_mantle_dex_protocol_volume(data, slug)
        if total_24h is None:
            return []
        return [
            MetricRecord(
                scope="ecosystem",
                entity=slug,
                metric_name="volume",
                value=Decimal(str(total_24h)),
                unit="usd",
                source_platform="defillama",
                source_ref=None,
                collected_at=datetime.now(tz=timezone.utc),
            )
        ]

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.BASE}/v2/historicalChainTvl/Mantle")
            return resp.status_code == 200
        except Exception:
            return False

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
