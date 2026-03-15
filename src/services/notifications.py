from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

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
            app_id=settings.lark_app_id,
            app_secret=settings.lark_app_secret,
        )

    async def deliver_alerts(self, alerts: list[AlertEvent]) -> None:
        if not self._settings.lark_delivery_enabled or not alerts:
            return

        chat_id = self._resolve_chat_id("alert")
        if not chat_id:
            logger.warning("Skipping Lark alert delivery because no chat id is configured")
            return

        for alert in alerts:
            logical_key = self._logical_key("lark_alert", "alert", alert.id)
            async with self._session_factory() as session:
                delivery = await get_delivery_event_by_logical_key(session, logical_key)
                if delivery is None:
                    delivery = await create_delivery_event(
                        session,
                        channel="lark_alert",
                        entity_type="alert",
                        entity_id=alert.id,
                        logical_key=logical_key,
                        environment=self._settings.lark_environment,
                        status="pending",
                        attempt_count=0,
                        created_at=datetime.now(tz=timezone.utc),
                        updated_at=datetime.now(tz=timezone.utc),
                    )
                elif delivery.status == "delivered":
                    continue

                try:
                    await self._lark_client.send_card(
                        chat_id=chat_id,
                        card=build_alert_card(self._serialize_alert(alert)),
                    )
                except Exception as exc:
                    logger.exception("Failed to deliver alert %s to Lark", alert.id)
                    await mark_delivery_event_failed(session, delivery, error=str(exc))
                else:
                    await mark_delivery_event_delivered(
                        session,
                        delivery,
                        delivered_at=datetime.now(tz=timezone.utc),
                    )

                await session.commit()

    def _resolve_chat_id(self, channel: str) -> str:
        environment = self._settings.lark_environment.lower()
        if channel == "alert":
            if environment == "prod":
                return self._settings.lark_alert_chat_id_prod
            return self._settings.lark_alert_chat_id_dev
        if channel == "summary":
            if environment == "prod":
                return self._settings.lark_summary_chat_id_prod
            return self._settings.lark_summary_chat_id_dev
        raise ValueError(f"Unsupported Lark channel: {channel}")

    def _logical_key(self, channel: str, entity_type: str, entity_id: int | None) -> str:
        return f"{self._settings.lark_environment}:{channel}:{entity_type}:{entity_id}"

    def _serialize_alert(self, alert: AlertEvent) -> dict[str, str | None]:
        return {
            "entity": alert.entity,
            "metric_name": alert.metric_name,
            "current_value": _decimal_to_str(alert.current_value),
            "formatted_value": alert.formatted_value,
            "time_window": alert.time_window,
            "severity": alert.severity,
            "trigger_reason": alert.trigger_reason,
            "source_ref": alert.source_ref,
        }
