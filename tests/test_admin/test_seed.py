from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from config.settings import Settings
from src.admin.rebuild import (
    DATA_QUALITY_HISTORY_TARGETS,
    REBUILD_JOB_ORDER,
    rebuild_data_quality_history,
)
from src.admin.seed import seed_alert_scenario, seed_alert_scenarios, seed_alert_spike
from src.db.models import AlertEvent, MetricSnapshot
from src.scheduler.runtime import JobResult
from src.services.notifications import NotificationService


class FakeNotificationService:
    def __init__(self):
        self.calls: list[list[AlertEvent]] = []

    async def deliver_alerts(self, alerts):
        self.calls.append(list(alerts))


def _make_notification_settings(local_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///ignored.db",
        lark_delivery_enabled=False,
        alert_local_output_enabled=True,
        alert_local_output_dir=str(local_dir),
        lark_environment="prod",
    )


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


async def test_seed_alert_scenario_creates_expected_threshold_alerts(session_factory):
    result = await seed_alert_scenario(session_factory, "threshold_up_7d_tvl")

    assert result["scenario"] == "threshold_up_7d_tvl"
    assert result["snapshots_inserted"] == 8
    assert result["alerts_created"] >= 1
    assert result["expected_trigger_reasons"] == result["actual_trigger_reasons"]


async def test_seed_alert_scenario_keeps_low_coverage_series_silent(session_factory):
    result = await seed_alert_scenario(session_factory, "no_alert_low_coverage_7d")

    assert result["scenario"] == "no_alert_low_coverage_7d"
    assert result["snapshots_inserted"] == 4
    assert result["alerts_created"] == 0
    assert result["actual_trigger_reasons"] == []

    async with session_factory() as session:
        alerts = (await session.execute(select(func.count()).select_from(AlertEvent))).scalar()

    assert alerts == 0


async def test_seed_alert_scenario_ath_tvl_reflects_current_real_path_limitation(session_factory):
    result = await seed_alert_scenario(session_factory, "ath_tvl")

    assert result["scenario"] == "ath_tvl"
    assert result["snapshots_inserted"] == 5
    assert result["alerts_created"] == 0
    assert result["expected_trigger_reasons"] == []
    assert result["actual_trigger_reasons"] == []
    assert "does not emit new_ath" in result["limitation"]


async def test_seed_alert_scenario_decline_7d_dau_matches_real_trigger_set(session_factory):
    result = await seed_alert_scenario(session_factory, "decline_7d_dau")

    assert result["scenario"] == "decline_7d_dau"
    assert result["expected_trigger_reasons"] == result["actual_trigger_reasons"]


async def test_seed_alert_scenario_threshold_mtd_active_addresses_matches_real_trigger_set(session_factory):
    result = await seed_alert_scenario(session_factory, "threshold_mtd_active_addresses")

    assert result["scenario"] == "threshold_mtd_active_addresses"
    assert result["expected_trigger_reasons"] == result["actual_trigger_reasons"]


async def test_seed_alert_scenario_multi_signal_core_matches_real_trigger_set(session_factory):
    result = await seed_alert_scenario(session_factory, "multi_signal_core")

    assert result["scenario"] == "multi_signal_core"
    assert result["expected_trigger_reasons"] == result["actual_trigger_reasons"]


async def test_seed_alert_scenario_delivers_created_alerts_to_notification_service(session_factory):
    notification_service = FakeNotificationService()

    result = await seed_alert_scenario(
        session_factory,
        "threshold_up_7d_tvl",
        notification_service=notification_service,
    )

    assert result["alerts_created"] == 1
    assert len(notification_service.calls) == 1
    assert [alert.trigger_reason for alert in notification_service.calls[0]] == result["actual_trigger_reasons"]


async def test_seed_alert_scenario_skips_notification_delivery_when_no_alerts(session_factory):
    notification_service = FakeNotificationService()

    result = await seed_alert_scenario(
        session_factory,
        "no_alert_low_coverage_7d",
        notification_service=notification_service,
    )

    assert result["alerts_created"] == 0
    assert notification_service.calls == []


async def test_seed_alert_scenarios_batch_delivers_created_alerts_only_for_positive_scenarios(session_factory):
    notification_service = FakeNotificationService()

    result = await seed_alert_scenarios(
        session_factory,
        ["threshold_up_7d_tvl", "no_alert_low_coverage_7d"],
        notification_service=notification_service,
    )

    assert result["total_alerts_created"] == 1
    assert len(notification_service.calls) == 1
    assert [alert.trigger_reason for alert in notification_service.calls[0]] == ["threshold_25pct_7d"]


async def test_seed_alert_scenario_writes_local_log_when_notification_service_enabled(
    session_factory,
    tmp_path,
):
    local_dir = tmp_path / "logs" / "alerts"
    notification_service = NotificationService(
        settings=_make_notification_settings(local_dir),
        session_factory=session_factory,
    )

    result = await seed_alert_scenario(
        session_factory,
        "threshold_up_7d_tvl",
        notification_service=notification_service,
    )

    assert result["alerts_created"] == 1
    files = sorted(local_dir.glob("*.log"))
    assert len(files) == 1
    assert "threshold_25pct_7d" in files[0].name


async def test_seed_alert_scenario_consolidates_multi_alert_into_single_log(
    session_factory,
    tmp_path,
):
    local_dir = tmp_path / "logs" / "alerts"
    notification_service = NotificationService(
        settings=_make_notification_settings(local_dir),
        session_factory=session_factory,
    )

    result = await seed_alert_scenario(
        session_factory,
        "decline_7d_dau",
        notification_service=notification_service,
    )

    assert result["alerts_created"] == 3
    files = sorted(local_dir.glob("*.log"))
    assert len(files) == 1
    assert "3signals" in files[0].name

    content = files[0].read_text(encoding="utf-8")
    assert "Triggers:" in content
    assert "decline_25pct_7d" in content
    assert "threshold_25pct_7d" in content


async def test_seed_alert_scenario_cooldown_repeat_block_suppresses_second_duplicate(session_factory):
    result = await seed_alert_scenario(session_factory, "cooldown_repeat_block")

    assert result["scenario"] == "cooldown_repeat_block"
    assert result["first_alerts_created"] >= 1
    assert result["second_alerts_created"] == 0
    assert "threshold_25pct_7d" in result["first_trigger_reasons"]
    assert result["second_trigger_reasons"] == []


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
