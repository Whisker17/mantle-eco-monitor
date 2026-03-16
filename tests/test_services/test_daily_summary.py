from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot
from src.services.daily_summary import DailySummaryService


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.messages: list[dict] | None = None

    async def complete(self, messages: list[dict]) -> str:
        self.messages = messages
        return self.response


class FakeNotificationService:
    def __init__(self):
        self.calls: list[dict] = []

    async def deliver_summary(self, summary_key: str, card: dict) -> None:
        self.calls.append({"summary_key": summary_key, "card": card})


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "daily_summary.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_summary_service_summarizes_previous_shanghai_day_and_sends_card(
    session_factory,
):
    async with session_factory() as session:
        session.add_all(
            [
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="tvl",
                    value=Decimal("1000"),
                    formatted_value="$1.0K",
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://excluded.example/source",
                    collected_at=datetime(2026, 3, 14, 15, 30, tzinfo=UTC),
                    created_at=datetime(2026, 3, 14, 15, 30, tzinfo=UTC),
                ),
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="tvl",
                    value=Decimal("1500"),
                    formatted_value="$1.5K",
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/chain/Mantle",
                    collected_at=datetime(2026, 3, 14, 16, 30, tzinfo=UTC),
                    created_at=datetime(2026, 3, 14, 16, 30, tzinfo=UTC),
                ),
                AlertEvent(
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
                    detected_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                    is_ath=True,
                    is_milestone=False,
                    milestone_label=None,
                    cooldown_until=None,
                    reviewed=False,
                    ai_eligible=False,
                    created_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    llm_client = FakeLLMClient("TVL finished higher and triggered a strong alert.")
    notification_service = FakeNotificationService()
    service = DailySummaryService(
        session_factory=session_factory,
        llm_client=llm_client,
        notification_service=notification_service,
        timezone_name="Asia/Shanghai",
    )

    result = await service.send_previous_day_summary(
        now=datetime(2026, 3, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    )

    assert result["status"] == "sent"
    assert result["summary_key"] == "2026-03-15"
    assert llm_client.messages is not None
    assert "https://defillama.com/chain/Mantle" in llm_client.messages[-1]["content"]
    assert "https://excluded.example/source" not in llm_client.messages[-1]["content"]
    assert notification_service.calls[0]["summary_key"] == "2026-03-15"

    text_blocks = [
        element["content"]
        for element in notification_service.calls[0]["card"]["elements"]
        if element["tag"] == "markdown"
    ]
    assert any("TVL finished higher and triggered a strong alert." in block for block in text_blocks)
    assert any("https://defillama.com/chain/Mantle" in block for block in text_blocks)
