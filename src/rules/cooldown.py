from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.thresholds import COOLDOWN_HOURS
from src.db.models import AlertEvent
from src.rules.engine import AlertCandidate


async def apply_cooldown(
    candidates: list[AlertCandidate],
    session: AsyncSession,
) -> list[AlertCandidate]:
    filtered: list[AlertCandidate] = []
    now = datetime.now(tz=timezone.utc)

    for c in candidates:
        last = await _get_last_alert(session, c.entity, c.metric_name, c.trigger_reason)
        if last and last.cooldown_until and last.cooldown_until > now:
            continue
        hours = COOLDOWN_HOURS.get(c.severity, 48)
        c.cooldown_until = now + timedelta(hours=hours)
        filtered.append(c)

    return _suppress_lower_when_multi_signal(filtered)


async def _get_last_alert(
    session: AsyncSession,
    entity: str,
    metric_name: str,
    trigger_reason: str,
) -> AlertEvent | None:
    stmt = (
        select(AlertEvent)
        .where(
            AlertEvent.entity == entity,
            AlertEvent.metric_name == metric_name,
            AlertEvent.trigger_reason == trigger_reason,
        )
        .order_by(AlertEvent.detected_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _suppress_lower_when_multi_signal(candidates: list[AlertCandidate]) -> list[AlertCandidate]:
    multi_entities = {
        c.entity for c in candidates if c.trigger_reason.startswith("multi_signal:")
    }
    if not multi_entities:
        return candidates

    return [
        c for c in candidates
        if c.entity not in multi_entities
        or c.trigger_reason.startswith("multi_signal:")
        or c.severity in ("high", "critical")
    ]
