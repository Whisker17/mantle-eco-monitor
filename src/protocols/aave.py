from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.ingestion.base import MetricRecord
from src.protocols.base import ProtocolAdapter


class AaveAdapter(ProtocolAdapter):
    SLUG = "aave-v3"
    DEFILLAMA_URL = "https://api.llama.fi/protocol/aave-v3"

    @property
    def slug(self) -> str:
        return self.SLUG

    @property
    def monitoring_tier(self) -> str:
        return "special"

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        resp = await http.get(self.DEFILLAMA_URL)
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data)

    async def collect_history(
        self,
        http: httpx.AsyncClient,
        *,
        days: int,
        today: date | None = None,
    ) -> list[MetricRecord]:
        resp = await http.get(self.DEFILLAMA_URL)
        resp.raise_for_status()
        data = resp.json()
        records = self._parse_history(data)
        anchor = today or datetime.now(tz=timezone.utc).date()
        cutoff = anchor - timedelta(days=max(days, 0))
        return [record for record in records if record.collected_at.date() >= cutoff]

    def _parse(self, data: dict) -> list[MetricRecord]:
        chain_tvls = data.get("chainTvls", {})

        supply_entries = chain_tvls.get("Mantle", {}).get("tvl", [])
        borrow_entries = chain_tvls.get("Mantle-borrowed", {}).get("tvl", [])

        if not supply_entries:
            return []

        latest_supply = supply_entries[-1]
        supply = Decimal(str(latest_supply.get("totalLiquidityUSD", 0)))
        ts = datetime.fromtimestamp(latest_supply["date"], tz=timezone.utc)

        borrowed = Decimal("0")
        if borrow_entries:
            borrowed = Decimal(str(borrow_entries[-1].get("totalLiquidityUSD", 0)))

        utilization = borrowed / supply if supply > 0 else Decimal("0")
        tvl = supply

        return [
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="supply",
                value=supply, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="borrowed",
                value=borrowed, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="utilization",
                value=utilization, unit="percent", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
            MetricRecord(
                scope="ecosystem", entity="aave-v3", metric_name="tvl",
                value=tvl, unit="usd", source_platform="defillama",
                source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                collected_at=ts,
            ),
        ]

    def _parse_history(self, data: dict) -> list[MetricRecord]:
        chain_tvls = data.get("chainTvls", {})
        supply_entries = chain_tvls.get("Mantle", {}).get("tvl", [])
        borrow_entries = chain_tvls.get("Mantle-borrowed", {}).get("tvl", [])
        borrowed_by_ts = {
            int(entry["date"]): Decimal(str(entry.get("totalLiquidityUSD", 0)))
            for entry in borrow_entries
            if entry.get("date") is not None
        }

        records: list[MetricRecord] = []
        for entry in supply_entries:
            timestamp = entry.get("date")
            if timestamp is None:
                continue
            supply = Decimal(str(entry.get("totalLiquidityUSD", 0)))
            borrowed = borrowed_by_ts.get(int(timestamp), Decimal("0"))
            utilization = borrowed / supply if supply > 0 else Decimal("0")
            tvl = supply
            ts = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            records.extend(
                [
                    MetricRecord(
                        scope="ecosystem",
                        entity="aave-v3",
                        metric_name="supply",
                        value=supply,
                        unit="usd",
                        source_platform="defillama",
                        source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                        collected_at=ts,
                    ),
                    MetricRecord(
                        scope="ecosystem",
                        entity="aave-v3",
                        metric_name="borrowed",
                        value=borrowed,
                        unit="usd",
                        source_platform="defillama",
                        source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                        collected_at=ts,
                    ),
                    MetricRecord(
                        scope="ecosystem",
                        entity="aave-v3",
                        metric_name="utilization",
                        value=utilization,
                        unit="percent",
                        source_platform="defillama",
                        source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                        collected_at=ts,
                    ),
                    MetricRecord(
                        scope="ecosystem",
                        entity="aave-v3",
                        metric_name="tvl",
                        value=tvl,
                        unit="usd",
                        source_platform="defillama",
                        source_ref=f"https://defillama.com/protocol/{self.SLUG}",
                        collected_at=ts,
                    ),
                ]
            )
        return records
