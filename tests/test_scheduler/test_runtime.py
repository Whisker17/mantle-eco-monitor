from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot, SourceRun, WatchlistProtocol
from src.ingestion.base import BaseCollector, MetricRecord
from src.scheduler.runtime import refresh_watchlist, run_collection_job, run_source_health_job


class FakeCollector(BaseCollector):
    def __init__(
        self,
        *,
        source_platform: str,
        records: list[MetricRecord] | None = None,
        error: Exception | None = None,
        health_ok: bool = True,
    ):
        self._source_platform = source_platform
        self._records = records or []
        self._error = error
        self._health_ok = health_ok

    @property
    def source_platform(self) -> str:
        return self._source_platform

    async def collect(self) -> list[MetricRecord]:
        if self._error is not None:
            raise self._error
        return self._records

    async def health_check(self) -> bool:
        if self._error is not None:
            raise self._error
        return self._health_ok


class FakeWatchlistManager:
    def __init__(self, protocols: list[dict] | None = None, error: Exception | None = None):
        self._protocols = protocols or []
        self._error = error

    def get_seed(self) -> list[dict]:
        return [
            {
                "slug": "aave-v3",
                "display_name": "Aave V3",
                "category": "lending",
                "tier": "special",
                "pinned": True,
                "metrics": ["tvl", "supply", "borrowed", "utilization"],
            }
        ]

    async def fetch_mantle_protocols(self) -> list[dict]:
        if self._error is not None:
            raise self._error
        return self._protocols

    def score_and_rank(self, protocols: list[dict]) -> list[dict]:
        ranked = []
        for protocol in protocols:
            ranked.append({**protocol, "_category": protocol["category"].lower(), "_score": protocol["tvl"]})
        return ranked

    def build_watchlist(self, ranked_protocols: list[dict], pinned_slugs: set[str] | None = None) -> list[dict]:
        entries = self.get_seed()
        for protocol in ranked_protocols:
            entries.append(
                {
                    "slug": protocol["slug"],
                    "display_name": protocol["name"],
                    "category": protocol["category"].lower(),
                    "tier": "dex" if "dex" in protocol["category"].lower() else "generic",
                    "pinned": False,
                    "metrics": ["tvl", "volume"] if "dex" in protocol["category"].lower() else ["tvl"],
                }
            )
        return entries


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "runtime.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_collection_job_persists_snapshots_source_run_and_alerts(session_factory):
    now = datetime.now(tz=timezone.utc)

    async with session_factory() as session:
        session.add(
            MetricSnapshot(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("1000000000"),
                unit="usd",
                source_platform="defillama",
                source_ref=None,
                collected_at=now - timedelta(days=8),
                created_at=now,
            )
        )
        await session.commit()

    collector = FakeCollector(
        source_platform="defillama",
        records=[
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("1300000000"),
                unit="usd",
                source_platform="defillama",
                source_ref=None,
                collected_at=now,
            )
        ],
    )

    result = await run_collection_job("core_defillama", collector, session_factory)

    assert result.status == "success"
    assert result.records_collected == 1
    assert result.alerts_created >= 1

    async with session_factory() as session:
        snapshots = (await session.execute(select(MetricSnapshot))).scalars().all()
        alerts = (await session.execute(select(AlertEvent))).scalars().all()
        runs = (await session.execute(select(SourceRun))).scalars().all()

    assert len(snapshots) == 2
    assert len(alerts) >= 1
    assert len(runs) == 1
    assert runs[0].job_name == "core_defillama"
    assert runs[0].source_platform == "defillama"
    assert runs[0].status == "success"


@pytest.mark.asyncio
async def test_run_collection_job_records_failure_source_run(session_factory):
    collector = FakeCollector(
        source_platform="growthepie",
        error=RuntimeError("boom"),
    )

    result = await run_collection_job("core_growthepie", collector, session_factory)

    assert result.status == "failed"
    assert result.records_collected == 0

    async with session_factory() as session:
        runs = (await session.execute(select(SourceRun))).scalars().all()
        snapshots = (await session.execute(select(MetricSnapshot))).scalars().all()

    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "boom" in (runs[0].error_message or "")
    assert snapshots == []


@pytest.mark.asyncio
async def test_refresh_watchlist_fetches_dynamic_protocols_and_upserts_entries(session_factory):
    manager = FakeWatchlistManager(
        protocols=[
            {"slug": "merchant-moe-dex", "name": "Merchant Moe", "category": "Dexes", "tvl": 100_000_000},
            {"slug": "ondo-yield-assets", "name": "Ondo Yield Assets", "category": "RWA", "tvl": 50_000_000},
        ]
    )

    count = await refresh_watchlist(session_factory, manager)

    assert count == 3

    async with session_factory() as session:
        rows = (await session.execute(select(WatchlistProtocol).order_by(WatchlistProtocol.slug))).scalars().all()

    slugs = [row.slug for row in rows]
    assert "aave-v3" in slugs
    assert "merchant-moe-dex" in slugs
    assert "ondo-yield-assets" in slugs


@pytest.mark.asyncio
async def test_run_source_health_job_records_each_source_status(session_factory):
    collectors = [
        FakeCollector(source_platform="defillama", health_ok=True),
        FakeCollector(source_platform="l2beat", health_ok=False),
    ]

    results = await run_source_health_job(session_factory, collectors)

    assert results["defillama"] == "success"
    assert results["l2beat"] == "failed"

    async with session_factory() as session:
        runs = (await session.execute(select(SourceRun).order_by(SourceRun.source_platform))).scalars().all()

    assert len(runs) == 2
    assert runs[0].job_name == "source_health"
    assert {run.source_platform: run.status for run in runs} == {
        "defillama": "success",
        "l2beat": "failed",
    }


@pytest.mark.asyncio
async def test_run_collection_job_only_evaluates_latest_inserted_snapshot_per_metric(session_factory):
    now = datetime.now(tz=timezone.utc)

    collector = FakeCollector(
        source_platform="growthepie",
        records=[
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("100"),
                unit="usd",
                source_platform="growthepie",
                source_ref=None,
                collected_at=now - timedelta(days=6),
            ),
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("150"),
                unit="usd",
                source_platform="growthepie",
                source_ref=None,
                collected_at=now - timedelta(days=3),
            ),
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("200"),
                unit="usd",
                source_platform="growthepie",
                source_ref=None,
                collected_at=now,
            ),
        ],
    )

    result = await run_collection_job("core_growthepie", collector, session_factory)

    assert result.records_collected == 3
    assert result.alerts_created == 3


@pytest.mark.asyncio
async def test_run_collection_job_persists_dune_stablecoin_transfer_volume(session_factory):
    now = datetime.now(tz=timezone.utc)
    collector = FakeCollector(
        source_platform="dune",
        records=[
            MetricRecord(
                scope="core",
                entity="mantle",
                metric_name="stablecoin_transfer_volume",
                value=Decimal("2500000"),
                unit="usd",
                source_platform="dune",
                source_ref=None,
                collected_at=now,
            )
        ],
    )

    result = await run_collection_job("core_dune", collector, session_factory)

    assert result.status == "success"
    assert result.records_collected == 1

    async with session_factory() as session:
        snapshots = (
            await session.execute(
                select(MetricSnapshot).where(
                    MetricSnapshot.metric_name == "stablecoin_transfer_volume"
                )
            )
        ).scalars().all()
        runs = (
            await session.execute(
                select(SourceRun).where(SourceRun.job_name == "core_dune")
            )
        ).scalars().all()

    assert len(snapshots) == 1
    assert snapshots[0].value == Decimal("2500000")
    assert len(runs) == 1
    assert runs[0].source_platform == "dune"
    assert runs[0].status == "success"
