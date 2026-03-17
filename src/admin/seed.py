from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.repositories import insert_snapshots
from src.ingestion.base import MetricRecord
from src.rules.engine import RuleEngine


def _metric_unit(metric_name: str) -> str:
    if metric_name in {"daily_active_users", "active_addresses", "chain_transactions", "users"}:
        return "count"
    if metric_name == "utilization":
        return "ratio"
    return "usd"


def _make_record(
    *,
    entity: str,
    metric_name: str,
    value: str | int | Decimal,
    collected_at: datetime,
    scope: str = "core",
    source_ref: str = "admin://seed/scenario",
) -> MetricRecord:
    return MetricRecord(
        scope=scope,
        entity=entity,
        metric_name=metric_name,
        value=Decimal(str(value)),
        unit=_metric_unit(metric_name),
        source_platform="admin_seed",
        source_ref=source_ref,
        collected_at=collected_at,
    )


def _actual_trigger_reasons(candidates) -> list[str]:
    return sorted(candidate.trigger_reason for candidate in candidates)


async def _insert_records_and_evaluate(
    session_factory: async_sessionmaker[AsyncSession],
    records: list[MetricRecord],
) -> dict[str, Any]:
    async with session_factory() as session:
        return await _insert_records_and_evaluate_in_session(session, records)


async def _insert_records_and_evaluate_in_session(
    session: AsyncSession,
    records: list[MetricRecord],
) -> dict[str, Any]:
    inserted = await insert_snapshots(session, records)
    candidates = []
    alerts_created = 0
    if inserted:
        latest_at = max(snapshot.collected_at for snapshot in inserted)
        latest = [snapshot for snapshot in inserted if snapshot.collected_at == latest_at]
        candidates = await RuleEngine(session).evaluate(latest)
        alerts_created = await _persist_alerts(session, candidates)
    await session.commit()

    return {
        "snapshots_inserted": len(inserted),
        "alerts_created": alerts_created,
        "actual_trigger_reasons": _actual_trigger_reasons(candidates),
    }


async def _cooldown_repeat_block_result(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    import src.rules.cooldown as cooldown_module

    entity = "scenario-cooldown-repeat-block"
    first_records = [
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 8, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 9, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 10, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 11, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 12, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 13, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="100000000", collected_at=datetime(2026, 3, 14, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="125000000", collected_at=datetime(2026, 3, 15, 0, 0, tzinfo=UTC)),
    ]
    second_records = [
        _make_record(entity=entity, metric_name="tvl", value="125000000", collected_at=datetime(2026, 3, 16, 0, 0, tzinfo=UTC)),
    ]

    original_get_last_alert = cooldown_module._get_last_alert

    async def _normalized_get_last_alert(session: AsyncSession, entity: str, metric_name: str, trigger_reason: str):
        alert = await original_get_last_alert(session, entity, metric_name, trigger_reason)
        if alert is None:
            return None
        if alert.detected_at is not None and alert.detected_at.tzinfo is None:
            alert.detected_at = alert.detected_at.replace(tzinfo=UTC)
        if alert.cooldown_until is not None and alert.cooldown_until.tzinfo is None:
            alert.cooldown_until = alert.cooldown_until.replace(tzinfo=UTC)
        return alert

    # SQLite drops tzinfo on persisted datetimes; normalize on read so the real cooldown path can compare safely.
    cooldown_module._get_last_alert = _normalized_get_last_alert
    try:
        first = await _insert_records_and_evaluate(session_factory, first_records)
        second = await _insert_records_and_evaluate(session_factory, second_records)
    finally:
        cooldown_module._get_last_alert = original_get_last_alert

    return {
        "scenario": "cooldown_repeat_block",
        "snapshots_inserted": first["snapshots_inserted"] + second["snapshots_inserted"],
        "alerts_created": first["alerts_created"] + second["alerts_created"],
        "expected_trigger_reasons": ["threshold_25pct_7d"],
        "actual_trigger_reasons": first["actual_trigger_reasons"] + second["actual_trigger_reasons"],
        "first_alerts_created": first["alerts_created"],
        "second_alerts_created": second["alerts_created"],
        "first_trigger_reasons": first["actual_trigger_reasons"],
        "second_trigger_reasons": second["actual_trigger_reasons"],
    }


def _scenario_threshold_up_7d_tvl() -> dict[str, Any]:
    end = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    entity = "scenario-threshold-up-7d-tvl"
    values = ["100000000", "100000000", "100000000", "100000000", "100000000", "100000000", "100000000", "125000000"]
    records = [
        _make_record(
            entity=entity,
            metric_name="tvl",
            value=value,
            collected_at=end - timedelta(days=7 - offset),
        )
        for offset, value in enumerate(values)
    ]
    return {
        "scenario": "threshold_up_7d_tvl",
        "records": records,
        "expected_trigger_reasons": ["threshold_25pct_7d", "new_ath"],
    }


def _scenario_decline_7d_dau() -> dict[str, Any]:
    end = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    entity = "scenario-decline-7d-dau"
    values = ["1000", "1000", "1000", "1000", "1000", "1000", "1000", "750"]
    records = [
        _make_record(
            entity=entity,
            metric_name="daily_active_users",
            value=value,
            collected_at=end - timedelta(days=7 - offset),
        )
        for offset, value in enumerate(values)
    ]
    return {
        "scenario": "decline_7d_dau",
        "records": records,
        "expected_trigger_reasons": ["decline_25pct_7d"],
    }


def _scenario_threshold_mtd_active_addresses() -> dict[str, Any]:
    entity = "scenario-threshold-mtd-active-addresses"
    days = [1, 2, 3, 4, 5, 6, 8, 10]
    values = ["100", "102", "104", "106", "108", "110", "115", "120"]
    records = [
        _make_record(
            entity=entity,
            metric_name="active_addresses",
            value=value,
            collected_at=datetime(2026, 3, day, 0, 0, tzinfo=UTC),
        )
        for day, value in zip(days, values, strict=True)
    ]
    return {
        "scenario": "threshold_mtd_active_addresses",
        "records": records,
        "expected_trigger_reasons": ["threshold_20pct_mtd"],
    }


def _scenario_ath_tvl() -> dict[str, Any]:
    entity = "scenario-ath-tvl"
    records = [
        _make_record(entity=entity, metric_name="tvl", value="399000000", collected_at=datetime(2026, 2, 20, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="396000000", collected_at=datetime(2026, 3, 8, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="397000000", collected_at=datetime(2026, 3, 10, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="398000000", collected_at=datetime(2026, 3, 12, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="400000000", collected_at=datetime(2026, 3, 15, 0, 0, tzinfo=UTC)),
    ]
    return {
        "scenario": "ath_tvl",
        "records": records,
        "expected_trigger_reasons": ["new_ath"],
    }


def _scenario_milestone_tvl_1b() -> dict[str, Any]:
    entity = "scenario-milestone-tvl-1b"
    records = [
        _make_record(entity=entity, metric_name="tvl", value="1050000000", collected_at=datetime(2026, 2, 20, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="990000000", collected_at=datetime(2026, 3, 14, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="tvl", value="1010000000", collected_at=datetime(2026, 3, 15, 0, 0, tzinfo=UTC)),
    ]
    return {
        "scenario": "milestone_tvl_1b",
        "records": records,
        "expected_trigger_reasons": ["milestone_$1.00B"],
    }


def _scenario_multi_signal_core() -> dict[str, Any]:
    end = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    entity = "scenario-multi-signal-core"
    records: list[MetricRecord] = []
    for metric_name, current in (("tvl", "125000000"), ("dex_volume", "135000000")):
        values = ["100000000", "100000000", "100000000", "100000000", "100000000", "100000000", "100000000", current]
        records.extend(
            _make_record(
                entity=entity,
                metric_name=metric_name,
                value=value,
                collected_at=end - timedelta(days=7 - offset),
            )
            for offset, value in enumerate(values)
        )
    return {
        "scenario": "multi_signal_core",
        "records": records,
        "expected_trigger_reasons": ["multi_signal:dex_volume, tvl"],
    }


def _scenario_no_alert_low_coverage_7d() -> dict[str, Any]:
    entity = "scenario-no-alert-low-coverage-7d"
    records = [
        _make_record(entity=entity, metric_name="active_addresses", value="200", collected_at=datetime(2026, 3, 8, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="180", collected_at=datetime(2026, 3, 9, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="140", collected_at=datetime(2026, 3, 13, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="100", collected_at=datetime(2026, 3, 15, 0, 0, tzinfo=UTC)),
    ]
    return {
        "scenario": "no_alert_low_coverage_7d",
        "records": records,
        "expected_trigger_reasons": [],
    }


def _scenario_no_alert_sparse_mtd() -> dict[str, Any]:
    entity = "scenario-no-alert-sparse-mtd"
    records = [
        _make_record(entity=entity, metric_name="active_addresses", value="200", collected_at=datetime(2026, 3, 4, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="180", collected_at=datetime(2026, 3, 6, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="140", collected_at=datetime(2026, 3, 8, 0, 0, tzinfo=UTC)),
        _make_record(entity=entity, metric_name="active_addresses", value="100", collected_at=datetime(2026, 3, 10, 0, 0, tzinfo=UTC)),
    ]
    return {
        "scenario": "no_alert_sparse_mtd",
        "records": records,
        "expected_trigger_reasons": [],
    }


SCENARIO_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "threshold_up_7d_tvl": _scenario_threshold_up_7d_tvl,
    "decline_7d_dau": _scenario_decline_7d_dau,
    "threshold_mtd_active_addresses": _scenario_threshold_mtd_active_addresses,
    "ath_tvl": _scenario_ath_tvl,
    "milestone_tvl_1b": _scenario_milestone_tvl_1b,
    "multi_signal_core": _scenario_multi_signal_core,
    "no_alert_low_coverage_7d": _scenario_no_alert_low_coverage_7d,
    "no_alert_sparse_mtd": _scenario_no_alert_sparse_mtd,
}

ALERT_SCENARIO_NAMES = tuple(SCENARIO_BUILDERS.keys()) + ("cooldown_repeat_block",)


async def _persist_alerts(session: AsyncSession, candidates) -> int:
    now = datetime.now(tz=UTC)
    count = 0
    for candidate in candidates:
        await insert_alert(
            session,
            scope=candidate.scope,
            entity=candidate.entity,
            metric_name=candidate.metric_name,
            current_value=candidate.current_value,
            previous_value=candidate.previous_value,
            formatted_value=candidate.formatted_value,
            time_window=candidate.time_window,
            change_pct=candidate.change_pct,
            severity=candidate.severity,
            trigger_reason=candidate.trigger_reason,
            source_platform=candidate.source_platform,
            source_ref=candidate.source_ref,
            detected_at=now,
            is_ath=candidate.is_ath,
            is_milestone=candidate.is_milestone,
            milestone_label=candidate.milestone_label,
            cooldown_until=candidate.cooldown_until,
            reviewed=False,
            ai_eligible=False,
            created_at=now,
        )
        count += 1
    return count


async def seed_alert_spike(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    entity: str,
    metric: str,
    previous: str,
    current: str,
    evaluate_rules: bool = True,
    collected_at: datetime | None = None,
) -> dict[str, object]:
    now = collected_at or datetime.now(tz=UTC)
    previous_at = now - timedelta(days=7)
    records = [
        MetricRecord(
            scope="core",
            entity=entity,
            metric_name=metric,
            value=Decimal(previous),
            unit="usd",
            source_platform="admin_seed",
            source_ref="admin://seed/alert-spike",
            collected_at=previous_at,
        ),
        MetricRecord(
            scope="core",
            entity=entity,
            metric_name=metric,
            value=Decimal(current),
            unit="usd",
            source_platform="admin_seed",
            source_ref="admin://seed/alert-spike",
            collected_at=now,
        ),
    ]

    async with session_factory() as session:
        inserted = await insert_snapshots(session, records)
        alerts_created = 0
        if evaluate_rules and inserted:
            latest = max(inserted, key=lambda snapshot: snapshot.collected_at)
            candidates = await RuleEngine(session).evaluate([latest])
            alerts_created = await _persist_alerts(session, candidates)
        await session.commit()

    return {
        "entity": entity,
        "metric": metric,
        "snapshots_inserted": len(inserted),
        "alerts_created": alerts_created,
    }


async def seed_alert_scenario(
    session_factory: async_sessionmaker[AsyncSession],
    scenario_name: str,
) -> dict[str, Any]:
    if scenario_name == "cooldown_repeat_block":
        return await _cooldown_repeat_block_result(session_factory)

    builder = SCENARIO_BUILDERS.get(scenario_name)
    if builder is None:
        raise ValueError(f"Unknown alert seed scenario: {scenario_name}")

    scenario = builder()
    result = await _insert_records_and_evaluate(session_factory, scenario["records"])
    return {
        "scenario": scenario_name,
        "snapshots_inserted": result["snapshots_inserted"],
        "alerts_created": result["alerts_created"],
        "expected_trigger_reasons": scenario["expected_trigger_reasons"],
        "actual_trigger_reasons": result["actual_trigger_reasons"],
    }


async def seed_alert_scenarios(
    session_factory: async_sessionmaker[AsyncSession],
    scenario_names: list[str],
) -> dict[str, Any]:
    results = [await seed_alert_scenario(session_factory, scenario_name) for scenario_name in scenario_names]
    return {
        "scenarios": results,
        "total_snapshots_inserted": sum(int(result["snapshots_inserted"]) for result in results),
        "total_alerts_created": sum(int(result["alerts_created"]) for result in results),
    }
