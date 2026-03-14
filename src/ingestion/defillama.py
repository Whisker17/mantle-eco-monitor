from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import BaseCollector, MetricRecord

logger = logging.getLogger(__name__)


class DefiLlamaCollector(BaseCollector):
    BASE = "https://api.llama.fi"
    STABLES_BASE = "https://stablecoins.llama.fi"
    PROTOCOL_PATH = "/protocol"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def source_platform(self) -> str:
        return "defillama"

    async def collect(self) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        records.extend(await self._collect_chain_tvl())
        records.extend(await self._collect_stablecoin_supply())
        records.extend(await self._collect_stablecoin_mcap())
        records.extend(await self._collect_chain_dex_volume())
        return records

    async def _collect_chain_tvl(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.BASE}/v2/historicalChainTvl/Mantle")
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return []
        latest = data[-1]
        return [
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal(str(latest["tvl"])),
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com/chain/Mantle",
                collected_at=datetime.fromtimestamp(latest["date"], tz=timezone.utc),
            )
        ]

    async def _collect_stablecoin_supply(self) -> list[MetricRecord]:
        resp = await self._http.get(f"{self.STABLES_BASE}/stablecoincharts/Mantle")
        resp.raise_for_status()
        data = resp.json()
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
        resp = await self._http.get(f"{self.BASE}/overview/dexs/Mantle")
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
        resp = await self._http.get(f"{self.BASE}/summary/dexs/{slug}")
        resp.raise_for_status()
        data = resp.json()
        total_24h = data.get("total24h")
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
