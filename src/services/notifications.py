from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.db.models import AlertEvent
from src.db.repositories import (
    create_delivery_event,
    get_delivery_event_by_logical_key,
    mark_delivery_event_delivered,
    mark_delivery_event_failed,
)
from src.integrations.lark.cards import build_alert_card
from src.integrations.lark.client import LarkClient

logger = logging.getLogger(__name__)


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None

    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


class NotificationService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        lark_client: LarkClient | None = None,
    ):
        self._settings = settings
        self._session_factory = session_factory
        self._lark_client = lark_client or LarkClient(
            app_id=getattr(settings, "lark_app_id", ""),
            app_secret=getattr(settings, "lark_app_secret", ""),
            base_url=getattr(settings, "lark_base_url", "https://open.larksuite.com"),
        )

    async def deliver_alerts(self, alerts: list[AlertEvent]) -> None:
        if not alerts:
            return

        if getattr(self._settings, "lark_delivery_enabled", False):
            chat_id = self._resolve_chat_id("alert")
            if not chat_id:
                logger.warning("Skipping Lark alert delivery because no chat id is configured")
            else:
                for alert in alerts:
                    logical_key = self._logical_key("lark_alert", "alert", alert.id)
                    await self._deliver_card(
                        chat_id=chat_id,
                        channel="lark_alert",
                        entity_type="alert",
                        entity_id=alert.id,
                        logical_key=logical_key,
                        card=build_alert_card(self._serialize_alert(alert)),
                    )

        if getattr(self._settings, "alert_local_output_enabled", False):
            for alert in alerts:
                await self._deliver_local_alert(alert)

    async def deliver_summary(self, summary_key: str, card: dict) -> None:
        if not getattr(self._settings, "lark_delivery_enabled", False):
            return

        chat_id = self._resolve_chat_id("summary")
        if not chat_id:
            logger.warning("Skipping Lark summary delivery because no chat id is configured")
            return

        await self._deliver_card(
            chat_id=chat_id,
            channel="lark_summary",
            entity_type="summary",
            entity_id=None,
            logical_key=self._logical_key("lark_summary", "summary", summary_key),
            card=card,
        )

    def _resolve_chat_id(self, channel: str) -> str:
        environment = getattr(self._settings, "lark_environment", "dev").lower()
        if channel == "alert":
            if environment == "prod":
                return getattr(self._settings, "lark_alert_chat_id_prod", "")
            return getattr(self._settings, "lark_alert_chat_id_dev", "")
        if channel == "summary":
            if environment == "prod":
                return getattr(self._settings, "lark_summary_chat_id_prod", "")
            return getattr(self._settings, "lark_summary_chat_id_dev", "")
        raise ValueError(f"Unsupported Lark channel: {channel}")

    async def _deliver_card(
        self,
        *,
        chat_id: str,
        channel: str,
        entity_type: str,
        entity_id: int | None,
        logical_key: str,
        card: dict,
    ) -> None:
        async with self._session_factory() as session:
            delivery = await get_delivery_event_by_logical_key(session, logical_key)
            if delivery is None:
                delivery = await create_delivery_event(
                    session,
                    channel=channel,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    logical_key=logical_key,
                    environment=getattr(self._settings, "lark_environment", "dev"),
                    status="pending",
                    attempt_count=0,
                    created_at=datetime.now(tz=timezone.utc),
                    updated_at=datetime.now(tz=timezone.utc),
                )
            elif delivery.status == "delivered":
                return

            try:
                await self._lark_client.send_card(chat_id=chat_id, card=card)
            except Exception as exc:
                logger.exception("Failed to deliver %s %s to Lark", entity_type, entity_id)
                await mark_delivery_event_failed(session, delivery, error=str(exc))
            else:
                await mark_delivery_event_delivered(
                    session,
                    delivery,
                    delivered_at=datetime.now(tz=timezone.utc),
                )

            await session.commit()

    async def _deliver_local_alert(self, alert: AlertEvent) -> None:
        payload = self._serialize_alert(alert)
        logical_key = self._logical_key("local_alert_log", "alert", alert.id)

        async with self._session_factory() as session:
            delivery = await get_delivery_event_by_logical_key(session, logical_key)
            if delivery is None:
                delivery = await create_delivery_event(
                    session,
                    channel="local_alert_log",
                    entity_type="alert",
                    entity_id=alert.id,
                    logical_key=logical_key,
                    environment=getattr(self._settings, "lark_environment", "dev"),
                    status="pending",
                    attempt_count=0,
                    created_at=datetime.now(tz=timezone.utc),
                    updated_at=datetime.now(tz=timezone.utc),
                )
            elif delivery.status == "delivered":
                return

            try:
                path = self._local_alert_path(alert)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    self._render_local_alert_log(payload),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.exception("Failed to write local alert log for alert %s", alert.id)
                await mark_delivery_event_failed(session, delivery, error=str(exc))
            else:
                await mark_delivery_event_delivered(
                    session,
                    delivery,
                    delivered_at=datetime.now(tz=timezone.utc),
                )

            await session.commit()

    def _logical_key(self, channel: str, entity_type: str, entity_id: int | str | None) -> str:
        environment = getattr(self._settings, "lark_environment", "dev")
        return f"{environment}:{channel}:{entity_type}:{entity_id}"

    def _local_alert_path(self, alert: AlertEvent) -> Path:
        base_dir = Path(getattr(self._settings, "alert_local_output_dir", "logs/alerts"))
        if not base_dir.is_absolute():
            base_dir = Path.cwd() / base_dir

        detected_at = alert.detected_at or datetime.now(tz=timezone.utc)
        detected = detected_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        entity = self._sanitize_filename_part(alert.entity)
        metric = self._sanitize_filename_part(alert.metric_name)
        reason = self._sanitize_filename_part(alert.trigger_reason)
        filename = f"{detected}_{entity}_{metric}_{reason}_{alert.id}.log"
        return base_dir / filename

    def _sanitize_filename_part(self, value: str | None) -> str:
        if not value:
            return "unknown"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unknown"

    def _render_local_alert_log(self, alert: dict[str, str | bool | None]) -> str:
        card = build_alert_card(alert)
        blocks = [
            element["content"]
            for element in card.get("elements", [])
            if element.get("tag") == "markdown" and isinstance(element.get("content"), str)
        ]
        rendered = [self._normalize_local_block(block) for block in blocks]
        return "\n\n".join(rendered).strip() + "\n"

    def _normalize_local_block(self, block: str) -> str:
        prefix_map = {
            "📊 Metric:": "Metric:",
            "📈 Movement:": "Movement:",
            "📉 Movement:": "Movement:",
            "💰 Current Value:": "Current Value:",
            "🏆 Status:": "Status:",
            "📡 Source:": "Source:",
            "⏰ Detected:": "Detected:",
            "✍️ Suggested Draft Copy:": "Suggested Draft Copy:",
            "⚡ Action Required:": "Action Required:",
        }

        clean = block.replace("**", "").strip()
        lines = clean.splitlines() or [clean]
        if not lines:
            return clean

        first = lines[0]
        for raw_prefix, normalized in prefix_map.items():
            if first.startswith(raw_prefix):
                first = f"{normalized}{first[len(raw_prefix):]}"
                break
        lines[0] = first
        return "\n".join(lines)

    def _serialize_alert(self, alert: AlertEvent) -> dict[str, str | bool | None]:
        return {
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
            "detected_at": alert.detected_at.isoformat() if alert.detected_at else None,
            "is_ath": alert.is_ath,
            "is_milestone": alert.is_milestone,
            "milestone_label": alert.milestone_label,
        }
