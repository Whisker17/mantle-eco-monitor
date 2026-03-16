from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot
from src.db.repositories import get_metric_sync_state, insert_snapshots, upsert_metric_sync_state
from src.ingestion.base import MetricRecord
from src.ingestion.dune import DuneMetricSpec
from src.services.dune_sync import DuneSyncService


class FakeDuneClient:
    def __init__(self, results: dict[tuple[int, str, str], list[dict]]):
        self._results = results
        self.calls: list[tuple[int, dict[str, str] | None]] = []

    async def get_query_result(
        self,
        query_id: int,
        *,
        params: dict[str, str] | None = None,
    ) -> list[dict]:
        self.calls.append((query_id, params))
        if params is None:
            return []
        key = (query_id, params["start_date"], params["end_date"])
        return self._results.get(key, [])

    async def health_check(self) -> bool:
        return True


class FakeSettings:
    dune_api_key = "token"
    dune_daily_active_users_query_id = 42
    dune_active_addresses_query_id = 0
    dune_chain_transactions_query_id = 0
    dune_stablecoin_volume_query_id = 0
    dune_sync_correction_lookback_days = 2
    dune_sync_chunk_days = 31


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "dune_sync.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _specs(start_day: date) -> tuple[DuneMetricSpec, ...]:
    return (
        DuneMetricSpec(
            metric_name="daily_active_users",
            settings_attr="dune_daily_active_users_query_id",
            bootstrap_start=start_day,
        ),
    )


def _row(day: str, value: int) -> dict:
    return {"day": day, "value": value}


def _record(day: date, value: str) -> MetricRecord:
    return MetricRecord(
        scope="core",
        entity="mantle",
        metric_name="daily_active_users",
        value=Decimal(value),
        unit="count",
        source_platform="dune",
        source_ref=None,
        collected_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_dune_sync_service_bootstraps_metric_from_start_date(session_factory):
    client = FakeDuneClient(
        {
            (
                42,
                "2026-03-01",
                "2026-03-04",
            ): [
                _row("2026-03-01", 100),
                _row("2026-03-02", 120),
                _row("2026-03-03", 140),
                _row("2026-03-04", 160),
            ]
        }
    )
    service = DuneSyncService(
        settings=FakeSettings(),
        session_factory=session_factory,
        client=client,
        metric_specs=_specs(date(2026, 3, 1)),
    )

    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 5))

    assert result.metric_name == "daily_active_users"
    assert result.is_bootstrap is True
    assert result.fetch_start == date(2026, 3, 1)
    assert result.fetch_end == date(2026, 3, 4)
    assert result.records_written == 4
    assert result.advanced_to == date(2026, 3, 4)

    async with session_factory() as session:
        state = await get_metric_sync_state(
            session,
            source_platform="dune",
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
        )
        snapshots = (
            await session.execute(
                select(MetricSnapshot).order_by(MetricSnapshot.collected_day.asc())
            )
        ).scalars().all()

    assert state is not None
    assert state.last_synced_date == date(2026, 3, 4)
    assert state.last_backfilled_date == date(2026, 3, 4)
    assert state.backfill_status == "completed"
    assert [snapshot.value for snapshot in snapshots] == [
        Decimal("100"),
        Decimal("120"),
        Decimal("140"),
        Decimal("160"),
    ]


@pytest.mark.asyncio
async def test_dune_sync_service_catches_up_missing_days_with_correction_window(session_factory):
    async with session_factory() as session:
        await upsert_metric_sync_state(
            session,
            source_platform="dune",
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
            last_synced_date=date(2026, 3, 10),
            last_sync_status="success",
        )
        await session.commit()

    client = FakeDuneClient(
        {
            (
                42,
                "2026-03-09",
                "2026-03-14",
            ): [
                _row("2026-03-09", 90),
                _row("2026-03-10", 100),
                _row("2026-03-11", 110),
                _row("2026-03-12", 120),
                _row("2026-03-13", 130),
                _row("2026-03-14", 140),
            ]
        }
    )
    service = DuneSyncService(
        settings=FakeSettings(),
        session_factory=session_factory,
        client=client,
        metric_specs=_specs(date(2026, 3, 1)),
    )

    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 15))

    assert result.is_bootstrap is False
    assert result.backlog_days == 4
    assert result.fetch_start == date(2026, 3, 9)
    assert result.fetch_end == date(2026, 3, 14)
    assert client.calls == [
        (
            42,
            {"start_date": "2026-03-09", "end_date": "2026-03-14"},
        )
    ]


@pytest.mark.asyncio
async def test_dune_sync_service_rewrites_corrected_days_via_upsert(session_factory):
    async with session_factory() as session:
        await insert_snapshots(
            session,
            [_record(date(2026, 3, 9), "100"), _record(date(2026, 3, 10), "105")],
        )
        await upsert_metric_sync_state(
            session,
            source_platform="dune",
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
            last_synced_date=date(2026, 3, 10),
            last_sync_status="success",
        )
        await session.commit()

    client = FakeDuneClient(
        {
            (
                42,
                "2026-03-09",
                "2026-03-11",
            ): [
                _row("2026-03-09", 125),
                _row("2026-03-10", 130),
                _row("2026-03-11", 135),
            ]
        }
    )
    service = DuneSyncService(
        settings=FakeSettings(),
        session_factory=session_factory,
        client=client,
        metric_specs=_specs(date(2026, 3, 1)),
    )

    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 12))

    assert result.records_written == 3

    async with session_factory() as session:
        snapshots = (
            await session.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.metric_name == "daily_active_users")
                .order_by(MetricSnapshot.collected_day.asc())
            )
        ).scalars().all()

    assert [snapshot.value for snapshot in snapshots] == [
        Decimal("125"),
        Decimal("130"),
        Decimal("135"),
    ]


@pytest.mark.asyncio
async def test_dune_sync_service_skips_alerts_when_backlog_exceeds_one_day(session_factory):
    async with session_factory() as session:
        await insert_snapshots(
            session,
            [
                _record(date(2026, 3, 1), "100"),
                _record(date(2026, 3, 2), "110"),
                _record(date(2026, 3, 3), "115"),
            ],
        )
        await upsert_metric_sync_state(
            session,
            source_platform="dune",
            scope="core",
            entity="mantle",
            metric_name="daily_active_users",
            last_synced_date=date(2026, 3, 3),
            last_sync_status="success",
        )
        await session.commit()

    client = FakeDuneClient(
        {
            (
                42,
                "2026-03-02",
                "2026-03-05",
            ): [
                _row("2026-03-02", 110),
                _row("2026-03-03", 115),
                _row("2026-03-04", 180),
                _row("2026-03-05", 240),
            ]
        }
    )
    service = DuneSyncService(
        settings=FakeSettings(),
        session_factory=session_factory,
        client=client,
        metric_specs=_specs(date(2026, 3, 1)),
    )

    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 6))

    assert result.backlog_days == 2
    assert result.alerts_created == 0

    async with session_factory() as session:
        alerts = (await session.execute(select(AlertEvent))).scalars().all()

    assert alerts == []
