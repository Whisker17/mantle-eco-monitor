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
    assert result["alerts_created"] >= 1

    async with session_factory() as session:
        snapshots = (await session.execute(select(func.count()).select_from(MetricSnapshot))).scalar()
        alerts = (await session.execute(select(func.count()).select_from(AlertEvent))).scalar()

    assert snapshots == 2
    assert alerts >= 1


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
