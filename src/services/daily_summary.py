from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import AlertEvent, MetricSnapshot
from src.integrations.lark.cards import build_daily_summary_card


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None

    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _serialize_snapshot(snapshot: MetricSnapshot) -> dict[str, str | None]:
    return {
        "scope": snapshot.scope,
        "entity": snapshot.entity,
        "metric_name": snapshot.metric_name,
        "value": _decimal_to_str(snapshot.value),
        "formatted_value": snapshot.formatted_value,
        "source_platform": snapshot.source_platform,
        "source_ref": snapshot.source_ref,
        "collected_at": snapshot.collected_at.isoformat(),
    }


def _serialize_alert(alert: AlertEvent) -> dict[str, str | bool | None]:
    return {
        "scope": alert.scope,
        "entity": alert.entity,
        "metric_name": alert.metric_name,
        "current_value": _decimal_to_str(alert.current_value),
        "formatted_value": alert.formatted_value,
        "time_window": alert.time_window,
        "change_pct": _decimal_to_str(alert.change_pct),
        "severity": alert.severity,
        "trigger_reason": alert.trigger_reason,
        "source_platform": alert.source_platform,
        "source_ref": alert.source_ref,
        "detected_at": alert.detected_at.isoformat(),
        "is_ath": alert.is_ath,
        "is_milestone": alert.is_milestone,
        "milestone_label": alert.milestone_label,
    }


class DailySummaryService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm_client,
        notification_service,
        timezone_name: str = "Asia/Shanghai",
    ):
        self._session_factory = session_factory
        self._llm_client = llm_client
        self._notification_service = notification_service
        self._timezone = ZoneInfo(timezone_name)

    async def send_previous_day_summary(self, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.now(tz=UTC)
        local_now = now.astimezone(self._timezone)
        summary_day = local_now.date() - timedelta(days=1)
        start_utc, end_utc = self._window_bounds(summary_day)
        context = await self._load_context(summary_day, start_utc, end_utc)

        if not context["metrics"] and not context["alerts"]:
            return {"status": "skipped", "summary_key": summary_day.isoformat(), "reason": "no_data"}

        summary_text = await self._llm_client.complete(
            [
                {
                    "role": "system",
                    "content": "Write a concise Mantle ecosystem daily summary using only the supplied JSON.",
                },
                {
                    "role": "user",
                    "content": json.dumps(context, sort_keys=True),
                },
            ]
        )

        card = build_daily_summary_card(
            {
                "title": "Mantle Daily Summary",
                "summary_text": summary_text,
                "metrics": context["metrics"],
                "alerts": context["alerts"],
            }
        )
        summary_key = summary_day.isoformat()
        await self._notification_service.deliver_summary(summary_key, card)
        return {
            "status": "sent",
            "summary_key": summary_key,
            "metrics_count": len(context["metrics"]),
            "alerts_count": len(context["alerts"]),
        }

    def _window_bounds(self, summary_day: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(summary_day, time.min, tzinfo=self._timezone)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    async def _load_context(
        self,
        summary_day: date,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            snapshots = (
                await session.execute(
                    select(MetricSnapshot)
                    .where(
                        MetricSnapshot.collected_at >= start_utc,
                        MetricSnapshot.collected_at < end_utc,
                    )
                    .order_by(MetricSnapshot.collected_at.desc())
                )
            ).scalars().all()
            alerts = (
                await session.execute(
                    select(AlertEvent)
                    .where(
                        AlertEvent.detected_at >= start_utc,
                        AlertEvent.detected_at < end_utc,
                    )
                    .order_by(AlertEvent.detected_at.desc())
                )
            ).scalars().all()

        latest_snapshots: dict[tuple[str, str, str], MetricSnapshot] = {}
        for snapshot in snapshots:
            key = (snapshot.scope, snapshot.entity, snapshot.metric_name)
            if key not in latest_snapshots:
                latest_snapshots[key] = snapshot

        return {
            "day": summary_day.isoformat(),
            "metrics": [_serialize_snapshot(snapshot) for snapshot in latest_snapshots.values()],
            "alerts": [_serialize_alert(alert) for alert in alerts],
        }
