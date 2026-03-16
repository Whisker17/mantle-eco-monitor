from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot, SourceRun, WatchlistProtocol
from src.ingestion.base import BaseCollector, MetricRecord
from src.scheduler.runtime import refresh_watchlist, run_collection_job, run_dune_sync_job, run_source_health_job
from src.services.dune_sync import DuneMetricSyncResult, DuneSyncResult


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


class FakeDuneSyncService:
    def __init__(self, result: DuneSyncResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def sync_all(self) -> DuneSyncResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


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
async def test_run_dune_sync_job_records_success_source_run(session_factory):
    result = DuneSyncResult(
        metrics_processed=1,
        records_written=6,
        alerts_created=0,
        metric_results=[
            DuneMetricSyncResult(
                metric_name="daily_active_users",
                fetch_start=datetime(2026, 3, 1, tzinfo=timezone.utc).date(),
                fetch_end=datetime(2026, 3, 6, tzinfo=timezone.utc).date(),
                advanced_to=datetime(2026, 3, 6, tzinfo=timezone.utc).date(),
                backlog_days=0,
                records_written=6,
                alerts_created=0,
                is_bootstrap=True,
            )
        ],
    )

    job_result = await run_dune_sync_job(
        "core_dune",
        FakeDuneSyncService(result=result),
        session_factory,
    )

    assert job_result.status == "success"
    assert job_result.records_collected == 6
    assert job_result.alerts_created == 0

    async with session_factory() as session:
        runs = (await session.execute(select(SourceRun))).scalars().all()

    assert len(runs) == 1
    assert runs[0].source_platform == "dune"
    assert runs[0].job_name == "core_dune"
    assert runs[0].status == "success"


@pytest.mark.asyncio
async def test_run_dune_sync_job_records_failure_source_run(session_factory):
    job_result = await run_dune_sync_job(
        "core_dune",
        FakeDuneSyncService(error=RuntimeError("dune boom")),
        session_factory,
    )

    assert job_result.status == "failed"
    assert job_result.records_collected == 0
    assert job_result.alerts_created == 0
    assert "dune boom" in (job_result.error_message or "")

    async with session_factory() as session:
        runs = (await session.execute(select(SourceRun))).scalars().all()

    assert len(runs) == 1
    assert runs[0].source_platform == "dune"
    assert runs[0].status == "failed"


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
async def test_run_collection_job_skips_identical_historical_replay(session_factory):
    now = datetime.now(tz=timezone.utc)
    records = [
        MetricRecord(
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
            value=Decimal("100"),
            unit="count",
            source_platform="growthepie",
            source_ref=None,
            collected_at=now - timedelta(days=2),
        ),
        MetricRecord(
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
            value=Decimal("150"),
            unit="count",
            source_platform="growthepie",
            source_ref=None,
            collected_at=now - timedelta(days=1),
        ),
    ]

    collector = FakeCollector(source_platform="growthepie", records=records)

    first = await run_collection_job("core_growthepie", collector, session_factory)
    second = await run_collection_job("core_growthepie", collector, session_factory)

    assert first.records_collected == 2
    assert second.records_collected == 0
    assert second.alerts_created == 0

    async with session_factory() as session:
        snapshots = (
            await session.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.metric_name == "daily_active_users")
                .order_by(MetricSnapshot.collected_day.asc())
            )
        ).scalars().all()

    assert len(snapshots) == 2


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


@pytest.mark.asyncio
async def test_run_collection_job_attempts_notification_after_commit_and_ignores_delivery_failure(
    session_factory,
):
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
                source_ref="https://defillama.com/chain/Mantle",
                collected_at=now - timedelta(days=8),
                created_at=now,
            )
        )
        await session.commit()

    class FailingNotificationService:
        def __init__(self):
            self.called = False
            self.visible_alert_count = 0

        async def deliver_alerts(self, alerts):
            self.called = True
            async with session_factory() as session:
                self.visible_alert_count = len(
                    (await session.execute(select(AlertEvent))).scalars().all()
                )
            raise RuntimeError("notify boom")

    notification_service = FailingNotificationService()
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
                source_ref="https://defillama.com/chain/Mantle",
                collected_at=now,
            )
        ],
    )

    result = await run_collection_job(
        "core_defillama",
        collector,
        session_factory,
        notification_service=notification_service,
    )

    async with session_factory() as session:
        alerts = (await session.execute(select(AlertEvent))).scalars().all()
        runs = (await session.execute(select(SourceRun))).scalars().all()

    assert result.status == "success"
    assert result.alerts_created >= 1
    assert notification_service.called is True
    assert notification_service.visible_alert_count >= 1
    assert len(alerts) >= 1
    assert len(runs) == 1
    assert runs[0].status == "success"
