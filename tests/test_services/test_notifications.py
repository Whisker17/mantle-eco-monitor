from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import Settings
from src.db.models import AlertEvent, Base, DeliveryEvent
from src.services.notifications import NotificationService


class FakeLarkClient:
    def __init__(self, *, error: Exception | None = None):
        self.calls: list[dict] = []
        self._error = error

    async def send_card(self, *, chat_id: str, card: dict):
        self.calls.append({"chat_id": chat_id, "card": card})
        if self._error is not None:
            raise self._error
        return {"data": {"message_id": "om_123"}}


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "notifications.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _insert_alert(session_factory):
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    async with session_factory() as session:
        alert = AlertEvent(
            scope="core",
            entity="mantle",
            metric_name="tvl",
            current_value=Decimal("1500"),
            previous_value=Decimal("1200"),
            formatted_value="$1.5K",
            time_window="7d",
            change_pct=Decimal("0.25"),
            severity="high",
            trigger_reason="TVL up 25% in 7d",
            source_platform="defillama",
            source_ref="https://defillama.com/chain/Mantle",
            detected_at=now,
            is_ath=True,
            is_milestone=False,
            milestone_label=None,
            cooldown_until=None,
            reviewed=False,
            ai_eligible=False,
            created_at=now,
        )
        session.add(alert)
        await session.commit()
        return alert


def _make_settings(**overrides):
    values = {
        "_env_file": None,
        "database_url": "sqlite+aiosqlite:///ignored.db",
        "lark_delivery_enabled": True,
        "lark_environment": "prod",
        "lark_alert_chat_id_dev": "chat_dev_alert",
        "lark_alert_chat_id_prod": "chat_prod_alert",
        "lark_summary_chat_id_dev": "chat_dev_summary",
        "lark_summary_chat_id_prod": "chat_prod_summary",
    }
    values.update(overrides)
    return Settings(
        **values,
    )


@pytest.mark.asyncio
async def test_notification_service_delivers_alerts_to_environment_chat_and_records_delivery(
    session_factory,
):
    alert = await _insert_alert(session_factory)
    client = FakeLarkClient()
    service = NotificationService(
        settings=_make_settings(lark_environment="prod"),
        session_factory=session_factory,
        lark_client=client,
    )

    await service.deliver_alerts([alert])

    async with session_factory() as session:
        deliveries = (await session.execute(select(DeliveryEvent))).scalars().all()

    assert client.calls[0]["chat_id"] == "chat_prod_alert"
    assert len(deliveries) == 1
    assert deliveries[0].status == "delivered"
    assert deliveries[0].attempt_count == 1
    assert deliveries[0].logical_key == f"prod:lark_alert:alert_group:{alert.entity}:{alert.id}"


@pytest.mark.asyncio
async def test_notification_service_skips_alert_delivery_when_disabled(session_factory):
    alert = await _insert_alert(session_factory)
    client = FakeLarkClient()
    service = NotificationService(
        settings=_make_settings(lark_delivery_enabled=False),
        session_factory=session_factory,
        lark_client=client,
    )

    await service.deliver_alerts([alert])

    async with session_factory() as session:
        deliveries = (await session.execute(select(DeliveryEvent))).scalars().all()

    assert client.calls == []
    assert deliveries == []


@pytest.mark.asyncio
async def test_notification_service_marks_failed_delivery_when_lark_send_raises(session_factory):
    alert = await _insert_alert(session_factory)
    service = NotificationService(
        settings=_make_settings(),
        session_factory=session_factory,
        lark_client=FakeLarkClient(error=RuntimeError("boom")),
    )

    await service.deliver_alerts([alert])

    async with session_factory() as session:
        deliveries = (await session.execute(select(DeliveryEvent))).scalars().all()

    assert len(deliveries) == 1
    assert deliveries[0].status == "failed"
    assert deliveries[0].attempt_count == 1
    assert deliveries[0].last_error == "boom"


@pytest.mark.asyncio
async def test_notification_service_serializes_alert_fields_needed_for_lark_card(
    session_factory,
    monkeypatch,
):
    import src.services.notifications as notifications_module

    alert = await _insert_alert(session_factory)
    client = FakeLarkClient()
    captured_payloads: list[list[dict]] = []

    def fake_build_consolidated_alert_card(payloads: list[dict]):
        captured_payloads.append(payloads)
        return {"header": {"title": {"tag": "plain_text", "content": "Alert"}}, "elements": []}

    monkeypatch.setattr(notifications_module, "build_consolidated_alert_card", fake_build_consolidated_alert_card)
    service = NotificationService(
        settings=_make_settings(),
        session_factory=session_factory,
        lark_client=client,
    )

    await service.deliver_alerts([alert])

    assert len(captured_payloads) == 1
    payload = captured_payloads[0][0]
    assert payload["change_pct"] == "0.25"
    assert payload["detected_at"] == "2026-03-15T10:00:00+00:00"
    assert payload["is_ath"] is True
    assert payload["is_milestone"] is False
    assert payload["milestone_label"] is None
    assert payload["source_platform"] == "defillama"


@pytest.mark.asyncio
async def test_notification_service_writes_local_alert_log_with_expected_field_order(
    session_factory,
    tmp_path,
):
    alert = await _insert_alert(session_factory)
    local_dir = tmp_path / "logs" / "alerts"
    service = NotificationService(
        settings=_make_settings(
            lark_delivery_enabled=False,
            alert_local_output_enabled=True,
            alert_local_output_dir=str(local_dir),
        ),
        session_factory=session_factory,
        lark_client=FakeLarkClient(),
    )

    await service.deliver_alerts([alert])

    files = sorted(local_dir.glob("*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")

    expected_order = [
        "Metric:",
        "Movement:",
        "Current Value:",
        "Status:",
        "Source:",
        "Detected:",
        "Suggested Draft Copy:",
        "Action Required:",
    ]
    positions = [content.index(label) for label in expected_order]
    assert positions == sorted(positions)
    assert "Metric: TVL (Total Value Locked)" in content
    assert "Status: NEW ALL-TIME HIGH" in content

    async with session_factory() as session:
        deliveries = (await session.execute(select(DeliveryEvent))).scalars().all()
    assert len(deliveries) == 1
    assert deliveries[0].channel == "local_alert_log"
    assert deliveries[0].logical_key == f"prod:local_alert_log:alert_group:{alert.entity}:{alert.id}"
    assert deliveries[0].status == "delivered"


@pytest.mark.asyncio
async def test_notification_service_writes_local_logs_without_lark_calls_when_lark_disabled(
    session_factory,
    tmp_path,
):
    alert = await _insert_alert(session_factory)
    local_dir = tmp_path / "logs" / "alerts"
    client = FakeLarkClient()
    service = NotificationService(
        settings=_make_settings(
            lark_delivery_enabled=False,
            alert_local_output_enabled=True,
            alert_local_output_dir=str(local_dir),
        ),
        session_factory=session_factory,
        lark_client=client,
    )

    await service.deliver_alerts([alert])

    assert client.calls == []
    files = sorted(local_dir.glob("*.log"))
    assert len(files) == 1
    assert Path(files[0]).exists()
