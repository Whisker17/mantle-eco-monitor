from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot
from src.services.query_tools import (
    get_daily_summary_context,
    get_latest_metric,
    get_metric_history,
    get_recent_alerts,
)


@pytest.fixture()
async def async_session(tmp_path):
    db_path = tmp_path / "services.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
async def seeded_session(async_session):
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    async_session.add_all(
        [
            MetricSnapshot(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("1200"),
                formatted_value="$1.2K",
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com/chain/Mantle",
                collected_at=now - timedelta(days=1),
                created_at=now - timedelta(days=1),
            ),
            MetricSnapshot(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("1500"),
                formatted_value="$1.5K",
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com/chain/Mantle",
                collected_at=now,
                created_at=now,
            ),
            MetricSnapshot(
                scope="core",
                entity="mantle",
                metric_name="dex_volume",
                value=Decimal("300"),
                formatted_value="$300",
                unit="usd",
                source_platform="defillama",
                source_ref="https://defillama.com/dexs/chain/mantle",
                collected_at=now,
                created_at=now,
            ),
            AlertEvent(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                current_value=Decimal("1500"),
                previous_value=Decimal("1200"),
                formatted_value="$1.5K",
                time_window="7d",
                change_pct=Decimal("0.25"),
                severity="high",
                trigger_reason="threshold_25pct_7d",
                source_platform="defillama",
                source_ref="https://defillama.com/chain/Mantle",
                detected_at=now,
                is_ath=True,
                is_milestone=False,
                milestone_label=None,
                cooldown_until=None,
                reviewed=False,
                ai_eligible=False,
                created_at=now,
            ),
        ]
    )
    await async_session.commit()
    return async_session


@pytest.mark.asyncio
async def test_get_latest_metric_returns_source_metadata(seeded_session):
    result = await get_latest_metric(seeded_session, entity="mantle", metric_name="tvl")

    assert result is not None
    assert result["entity"] == "mantle"
    assert result["metric_name"] == "tvl"
    assert result["value"] == "1500"
    assert result["source_platform"] == "defillama"
    assert result["source_ref"] == "https://defillama.com/chain/Mantle"


@pytest.mark.asyncio
async def test_get_metric_history_returns_descending_points_with_sources(seeded_session):
    result = await get_metric_history(
        seeded_session,
        entity="mantle",
        metric_name="tvl",
        since=datetime(2026, 3, 13, tzinfo=UTC),
        until=datetime(2026, 3, 15, 23, 59, tzinfo=UTC),
    )

    assert result["entity"] == "mantle"
    assert result["metric_name"] == "tvl"
    assert [point["value"] for point in result["points"]] == ["1500", "1200"]
    assert result["points"][0]["source_ref"] == "https://defillama.com/chain/Mantle"


@pytest.mark.asyncio
async def test_get_recent_alerts_returns_source_urls(seeded_session):
    result = await get_recent_alerts(seeded_session, limit=5)

    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["severity"] == "high"
    assert result["alerts"][0]["source_ref"] == "https://defillama.com/chain/Mantle"


@pytest.mark.asyncio
async def test_get_daily_summary_context_groups_metrics_and_alerts_for_day(seeded_session):
    result = await get_daily_summary_context(seeded_session, day=date(2026, 3, 15))

    assert result["day"] == "2026-03-15"
    assert {metric["metric_name"] for metric in result["metrics"]} == {"tvl", "dex_volume"}
    assert result["alerts"][0]["trigger_reason"] == "threshold_25pct_7d"
    assert result["alerts"][0]["source_ref"] == "https://defillama.com/chain/Mantle"
