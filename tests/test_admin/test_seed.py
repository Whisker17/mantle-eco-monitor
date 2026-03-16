from __future__ import annotations

from sqlalchemy import func, select

from src.admin.seed import seed_alert_spike
from src.db.models import AlertEvent, MetricSnapshot


async def test_seed_alert_spike_inserts_snapshots_and_alerts(session_factory):
    result = await seed_alert_spike(
        session_factory,
        entity="mantle",
        metric="tvl",
        previous="100",
        current="200",
    )

    assert result["entity"] == "mantle"
    assert result["metric"] == "tvl"
    assert result["snapshots_inserted"] == 2
    assert result["alerts_created"] == 0

    async with session_factory() as session:
        snapshots = (await session.execute(select(func.count()).select_from(MetricSnapshot))).scalar()
        alerts = (await session.execute(select(func.count()).select_from(AlertEvent))).scalar()

    assert snapshots == 2
    assert alerts == 0


async def test_clear_automated_history_removes_automated_snapshots_but_keeps_manual_ones(session_factory):
    from src.admin.rebuild import clear_automated_history
    from src.db.models import MetricSnapshot
    from datetime import datetime, UTC
    from decimal import Decimal

    now = datetime(2026, 3, 16, 10, 0, tzinfo=UTC)
    async with session_factory() as session:
        session.add_all(
            [
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="daily_active_users",
                    value=Decimal("123"),
                    unit="count",
                    source_platform="growthepie",
                    source_ref=None,
                    collected_at=now,
                    created_at=now,
                ),
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="daily_active_users",
                    value=Decimal("999"),
                    unit="count",
                    source_platform="admin_seed",
                    source_ref="admin://seed/manual",
                    collected_at=now.replace(day=15),
                    created_at=now,
                ),
            ]
        )
        await session.commit()

    result = await clear_automated_history(
        session_factory,
        targets=[{"scope": "core", "entity": "mantle", "metric_name": "daily_active_users"}],
    )

    assert result["snapshots_deleted"] == 1

    async with session_factory() as session:
        snapshots = (await session.execute(select(MetricSnapshot).order_by(MetricSnapshot.source_platform))).scalars().all()

    assert len(snapshots) == 1
    assert snapshots[0].source_platform == "admin_seed"


async def test_seed_alert_spike_skips_rule_evaluation_when_disabled(session_factory):
    result = await seed_alert_spike(
        session_factory,
        entity="mantle",
        metric="tvl",
        previous="100",
        current="200",
        evaluate_rules=False,
    )

    assert result["snapshots_inserted"] == 2
    assert result["alerts_created"] == 0

    async with session_factory() as session:
        snapshots = (await session.execute(select(func.count()).select_from(MetricSnapshot))).scalar()
        alerts = (await session.execute(select(func.count()).select_from(AlertEvent))).scalar()

    assert snapshots == 2
    assert alerts == 0
