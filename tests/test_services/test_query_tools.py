from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot, SourceRun, WatchlistProtocol
from src.services.query_tools import (
    get_alerts_list,
    get_daily_summary_context,
    get_health_status,
    get_latest_metric,
    get_metric_history,
    get_recent_alerts,
    get_source_health,
    get_watchlist,
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
            AlertEvent(
                scope="core",
                entity="methlab",
                metric_name="users",
                current_value=Decimal("120"),
                previous_value=Decimal("100"),
                formatted_value="120",
                time_window="1d",
                change_pct=Decimal("0.20"),
                severity="moderate",
                trigger_reason="users up 20% in 1d",
                source_platform="growthepie",
                source_ref="https://api.growthepie.com",
                detected_at=now - timedelta(hours=1),
                is_ath=False,
                is_milestone=False,
                milestone_label=None,
                cooldown_until=None,
                reviewed=True,
                ai_eligible=False,
                created_at=now,
            ),
            WatchlistProtocol(
                slug="aave-v3",
                display_name="Aave V3",
                category="lending",
                monitoring_tier="special",
                is_pinned=True,
                metrics=["tvl", "supply", "borrowed", "utilization"],
                active=True,
                added_at=now,
                updated_at=now,
            ),
            WatchlistProtocol(
                slug="merchant-moe-dex",
                display_name="Merchant Moe",
                category="dexes",
                monitoring_tier="dex",
                is_pinned=False,
                metrics=["tvl", "volume"],
                active=True,
                added_at=now,
                updated_at=now,
            ),
            SourceRun(
                source_platform="defillama",
                job_name="core_defillama",
                status="success",
                records_collected=3,
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=9),
                created_at=now,
            ),
            SourceRun(
                source_platform="l2beat",
                job_name="source_health",
                status="failed",
                records_collected=0,
                error_message="timeout",
                started_at=now - timedelta(minutes=8),
                completed_at=now - timedelta(minutes=8),
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

    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["severity"] == "high"
    assert result["alerts"][0]["source_ref"] == "https://defillama.com/chain/Mantle"


@pytest.mark.asyncio
async def test_get_alerts_list_applies_filters_and_returns_total(seeded_session):
    result = await get_alerts_list(
        seeded_session,
        entity="mantle",
        severity="high",
        reviewed=False,
        since=datetime(2026, 3, 14, tzinfo=UTC),
        until=datetime(2026, 3, 15, 23, 59, tzinfo=UTC),
        limit=10,
    )

    assert result["total"] == 1
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["entity"] == "mantle"
    assert result["alerts"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_get_health_status_returns_latest_source_state(seeded_session):
    result = await get_health_status(seeded_session)

    assert result["db"] == "connected"
    assert result["status"] == "degraded"
    assert result["last_source_runs"]["defillama"]["status"] == "success"
    assert result["last_source_runs"]["l2beat"]["status"] == "failed"
    assert result["last_source_runs"]["growthepie"]["status"] == "not_run"
    assert result["next_scheduled_run"] is None


@pytest.mark.asyncio
async def test_get_source_health_returns_recent_runs(seeded_session):
    result = await get_source_health(seeded_session, source_platform="defillama", limit=5)

    assert len(result["runs"]) == 1
    assert result["runs"][0]["source_platform"] == "defillama"
    assert result["runs"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_get_watchlist_returns_active_protocols(seeded_session):
    result = await get_watchlist(seeded_session)

    assert [protocol["slug"] for protocol in result["protocols"]] == ["aave-v3", "merchant-moe-dex"]
    assert result["protocols"][0]["is_pinned"] is True
    assert result["protocols"][0]["metrics"] == ["tvl", "supply", "borrowed", "utilization"]


@pytest.mark.asyncio
async def test_get_daily_summary_context_groups_metrics_and_alerts_for_day(seeded_session):
    result = await get_daily_summary_context(seeded_session, day=date(2026, 3, 15))

    assert result["day"] == "2026-03-15"
    assert {metric["metric_name"] for metric in result["metrics"]} == {"tvl", "dex_volume"}
    assert result["alerts"][0]["trigger_reason"] == "threshold_25pct_7d"
    assert result["alerts"][0]["source_ref"] == "https://defillama.com/chain/Mantle"
