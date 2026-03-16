from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot, SourceRun, WatchlistProtocol


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "admin.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture()
async def seeded_session(session_factory):
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    async with session_factory() as session:
        session.add_all(
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
                SourceRun(
                    source_platform="defillama",
                    job_name="core_defillama",
                    status="success",
                    records_collected=3,
                    started_at=now - timedelta(minutes=10),
                    completed_at=now - timedelta(minutes=9),
                    created_at=now,
                ),
            ]
        )
        await session.commit()
        yield session
