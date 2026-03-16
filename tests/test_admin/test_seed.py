from __future__ import annotations

import json

from sqlalchemy import func, select

from src.admin.rebuild import (
    DATA_QUALITY_HISTORY_TARGETS,
    REBUILD_JOB_ORDER,
    rebuild_data_quality_history,
)
from src.admin.seed import seed_alert_spike
from src.db.models import AlertEvent, MetricSnapshot
from src.scheduler.runtime import JobResult


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


def test_rebuild_data_quality_history_targets_include_core_tvl_and_mnt_volume():
    assert {"scope": "core", "entity": "mantle", "metric_name": "tvl"} in DATA_QUALITY_HISTORY_TARGETS
    assert {"scope": "core", "entity": "mantle", "metric_name": "mnt_volume"} in DATA_QUALITY_HISTORY_TARGETS


def test_rebuild_job_order_includes_core_history_jobs_before_ecosystem_jobs():
    assert REBUILD_JOB_ORDER == [
        "core_defillama",
        "core_dune",
        "core_coingecko",
        "watchlist_refresh",
        "eco_aave",
        "eco_protocols",
    ]


async def test_rebuild_data_quality_history_run_jobs_result_is_json_serializable(
    session_factory,
    monkeypatch,
):
    calls: list[str] = []

    async def fake_run_rebuild_job(job_id, *, settings, session_factory):
        calls.append(job_id)
        return JobResult(status="success", records_collected=1, alerts_created=0)

    monkeypatch.setattr("src.admin.rebuild._run_rebuild_job", fake_run_rebuild_job)

    result = await rebuild_data_quality_history(
        session_factory,
        settings=object(),
        apply=True,
        run_jobs=True,
    )
    payload = json.dumps(result)

    assert '"job_results"' in payload
    assert '"core_dune"' in payload
    assert calls == REBUILD_JOB_ORDER
