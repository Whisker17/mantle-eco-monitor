from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import AlertEvent
from src.db.repositories import insert_alert, insert_snapshots
from src.ingestion.base import MetricRecord
from src.rules.engine import RuleEngine


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
