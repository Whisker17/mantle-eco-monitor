from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.models import Base, AlertEvent, DeliveryEvent, MetricSnapshot, SourceRun
from src.db.repositories import (
    TimeWindow,
    create_delivery_event,
    get_comparison_snapshot,
    get_delivery_event_by_logical_key,
    get_previous_snapshot,
    insert_alert,
    insert_snapshots,
    insert_source_run,
    mark_delivery_event_delivered,
    mark_delivery_event_failed,
)
from src.ingestion.base import MetricRecord

# Use sync SQLite for simpler test setup
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


@pytest.fixture()
async def async_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


def _make_record(
    metric_name="tvl",
    value="1000",
    collected_at=None,
    entity="mantle",
    scope="core",
) -> MetricRecord:
    return MetricRecord(
        scope=scope,
        entity=entity,
        metric_name=metric_name,
        value=Decimal(value),
        unit="usd",
        source_platform="defillama",
        source_ref=None,
        collected_at=collected_at or datetime.now(tz=timezone.utc),
    )


@pytest.mark.asyncio
async def test_snapshot_repository_inserts_records(async_session):
    record = _make_record(value="1523000000")
    inserted = await insert_snapshots(async_session, [record])
    await async_session.commit()

    assert len(inserted) == 1
    assert inserted[0].value == Decimal("1523000000")


@pytest.mark.asyncio
async def test_snapshot_repository_skips_duplicate_daily_snapshot(async_session):
    now = datetime.now(tz=timezone.utc)
    r1 = _make_record(value="100", collected_at=now)
    r2 = _make_record(value="200", collected_at=now + timedelta(hours=2))

    inserted1 = await insert_snapshots(async_session, [r1])
    await async_session.commit()
    inserted2 = await insert_snapshots(async_session, [r2])
    await async_session.commit()

    assert len(inserted1) == 1
    assert len(inserted2) == 0  # deduped


@pytest.mark.asyncio
async def test_source_run_repository_records_success_and_failure(async_session):
    now = datetime.now(tz=timezone.utc)

    success = await insert_source_run(
        async_session,
        source_platform="defillama",
        job_name="core_tvl",
        status="success",
        records_collected=3,
        started_at=now,
        completed_at=now + timedelta(seconds=2),
        created_at=now,
    )
    await async_session.commit()
    assert success.status == "success"

    failure = await insert_source_run(
        async_session,
        source_platform="dune",
        job_name="core_dune",
        status="failed",
        error_message="timeout",
        records_collected=0,
        started_at=now,
        created_at=now,
    )
    await async_session.commit()
    assert failure.status == "failed"


@pytest.mark.asyncio
async def test_insert_alert(async_session):
    now = datetime.now(tz=timezone.utc)
    alert = await insert_alert(
        async_session,
        scope="core",
        entity="mantle",
        metric_name="tvl",
        current_value=Decimal("1600000000"),
        previous_value=Decimal("1400000000"),
        time_window="7d",
        change_pct=Decimal("0.1428"),
        severity="moderate",
        trigger_reason="threshold_14pct_7d",
        detected_at=now,
        is_ath=False,
        is_milestone=False,
        reviewed=False,
        ai_eligible=False,
        created_at=now,
    )
    await async_session.commit()
    assert alert.id is not None
    assert alert.severity == "moderate"


@pytest.mark.asyncio
async def test_get_comparison_snapshot_ath(async_session):
    now = datetime.now(tz=timezone.utc)
    records = [
        _make_record(value="100", collected_at=now - timedelta(days=10)),
        _make_record(value="500", collected_at=now - timedelta(days=5)),
        _make_record(value="300", collected_at=now - timedelta(days=1)),
    ]
    await insert_snapshots(async_session, records)
    await async_session.commit()

    ath = await get_comparison_snapshot(async_session, "mantle", "tvl", TimeWindow.ATH)
    assert ath is not None
    assert ath.value == Decimal("500")


@pytest.mark.asyncio
async def test_get_previous_snapshot(async_session):
    now = datetime.now(tz=timezone.utc)
    records = [
        _make_record(value="100", collected_at=now - timedelta(days=2)),
        _make_record(value="200", collected_at=now - timedelta(days=1)),
        _make_record(value="300", collected_at=now),
    ]
    await insert_snapshots(async_session, records)
    await async_session.commit()

    prev = await get_previous_snapshot(async_session, "mantle", "tvl")
    assert prev is not None
    assert prev.value == Decimal("200")


@pytest.mark.asyncio
async def test_create_delivery_event(async_session):
    event = await create_delivery_event(
        async_session,
        channel="lark_alert",
        entity_type="alert",
        entity_id=123,
        logical_key="dev:alert:123",
        environment="dev",
        status="pending",
        attempt_count=0,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    await async_session.commit()

    loaded = await get_delivery_event_by_logical_key(async_session, "dev:alert:123")

    assert event.id is not None
    assert loaded is not None
    assert loaded.channel == "lark_alert"
    assert loaded.status == "pending"


@pytest.mark.asyncio
async def test_mark_delivery_event_delivered(async_session):
    now = datetime.now(tz=timezone.utc)
    event = await create_delivery_event(
        async_session,
        channel="lark_summary",
        entity_type="summary",
        entity_id=None,
        logical_key="prod:summary:2026-03-15",
        environment="prod",
        status="pending",
        attempt_count=0,
        created_at=now,
        updated_at=now,
    )

    await mark_delivery_event_delivered(async_session, event, delivered_at=now + timedelta(minutes=1))
    await async_session.commit()

    assert event.status == "delivered"
    assert event.attempt_count == 1
    assert event.delivered_at == now + timedelta(minutes=1)
    assert event.last_error is None


@pytest.mark.asyncio
async def test_mark_delivery_event_failed_increments_attempt_count(async_session):
    now = datetime.now(tz=timezone.utc)
    event = await create_delivery_event(
        async_session,
        channel="lark_alert",
        entity_type="alert",
        entity_id=321,
        logical_key="prod:alert:321",
        environment="prod",
        status="pending",
        attempt_count=0,
        created_at=now,
        updated_at=now,
    )

    await mark_delivery_event_failed(async_session, event, error="timeout")
    await async_session.commit()

    reloaded = await async_session.get(DeliveryEvent, event.id)

    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.attempt_count == 1
    assert reloaded.last_error == "timeout"
