from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot
from src.services.bot_query import BotQueryService


class FakeLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self.messages: list[list[dict]] = []

    async def complete(self, messages: list[dict]) -> str:
        self.messages.append(messages)
        return self._responses.pop(0)


@pytest.fixture()
async def session_factory(tmp_path):
    db_path = tmp_path / "bot_query.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture()
async def seeded_data(session_factory):
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    async with session_factory() as session:
        session.add_all(
            [
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="tvl",
                    value=Decimal("1200"),
                    formatted_value="$1.2K",
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/chain/Mantle",
                    collected_at=now - timedelta(days=1),
                    created_at=now - timedelta(days=1),
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
                    collected_at=now,
                    created_at=now,
                ),
                MetricSnapshot(
                    scope="core",
                    entity="mantle",
                    metric_name="dex_volume",
                    value=Decimal("300"),
                    formatted_value="$300",
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/dexs/chain/mantle",
                    collected_at=now,
                    created_at=now,
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
                    detected_at=now,
                    is_ath=True,
                    is_milestone=False,
                    milestone_label=None,
                    cooldown_until=None,
                    reviewed=False,
                    ai_eligible=False,
                    created_at=now,
                ),
            ]
        )
        await session.commit()
    return now


@pytest.mark.asyncio
async def test_bot_query_service_handles_latest_metric_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"metric_latest","entity":"mantle","metric_name":"tvl"}',
            "Mantle TVL is $1.5K.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot mantle tvl latest", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert result["answer"] == "Mantle TVL is $1.5K."
    assert result["data"]["metric_name"] == "tvl"
    assert "https://defillama.com/chain/Mantle" in result["source_urls"]
    assert result["card"]["header"]["title"]["content"] == "Query Result"


@pytest.mark.asyncio
async def test_bot_query_service_handles_metric_history_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"metric_history","entity":"mantle","metric_name":"tvl","days":7}',
            "Mantle TVL rose over the last 7 days.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot show mantle tvl 7d", now=seeded_data)

    assert result["intent"] == "metric_history"
    assert result["answer"] == "Mantle TVL rose over the last 7 days."
    assert len(result["data"]["points"]) >= 2
    assert "https://defillama.com/chain/Mantle" in result["source_urls"]


@pytest.mark.asyncio
async def test_bot_query_service_handles_recent_alert_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"recent_alerts","entity":"mantle","limit":5}',
            "The latest alert is a high-severity TVL move.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot what are the latest mantle alerts", now=seeded_data)

    assert result["intent"] == "recent_alerts"
    assert result["answer"] == "The latest alert is a high-severity TVL move."
    assert result["data"]["alerts"][0]["severity"] == "high"
    assert "https://defillama.com/chain/Mantle" in result["source_urls"]


@pytest.mark.asyncio
async def test_bot_query_service_returns_supported_query_fallback_for_unsupported_prompt(
    session_factory,
    seeded_data,
):
    llm_client = FakeLLMClient(['{"intent":"unsupported"}'])
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot tell me a joke", now=seeded_data)

    assert result["intent"] == "unsupported"
    assert "latest metrics" in result["answer"]
    assert "history" in result["answer"]
    assert result["source_urls"] == []
