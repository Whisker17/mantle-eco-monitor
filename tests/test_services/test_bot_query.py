from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertEvent, Base, MetricSnapshot, SourceRun, WatchlistProtocol
from src.services.bot_catalog import build_bot_catalog
from src.services.bot_query import BotQueryService


class FakeLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self.messages: list[list[dict]] = []

    async def complete(self, messages: list[dict]) -> str:
        self.messages.append(messages)
        return self._responses.pop(0)


class RejectIntentParseLLMClient:
    def __init__(self, answer: str):
        self.answer = answer
        self.messages: list[list[dict]] = []

    async def complete(self, messages: list[dict]) -> str:
        self.messages.append(messages)
        if "Map the user message to JSON" in messages[0]["content"]:
            raise AssertionError("deterministic parser should have handled this request")
        return self.answer


class ForbiddenSessionFactory:
    def __call__(self):
        raise AssertionError("session_factory should not be used")


def test_metric_catalog_exposes_latest_and_history_capabilities():
    catalog = build_bot_catalog()

    assert "metric_latest" in catalog.intents
    assert "metric_history" in catalog.intents
    assert catalog.metric_aliases["TVL"] == "tvl"
    assert catalog.metric_aliases["dex volume"] == "dex_volume"


@pytest.mark.asyncio
async def test_bot_query_service_routes_query_mantle_tvl_without_llm_parser(session_factory, seeded_data):
    llm_client = RejectIntentParseLLMClient("Mantle TVL is $1.5K.")
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("query mantle tvl", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert result["data"]["metric_name"] == "tvl"
    assert result["answer"] == "Mantle TVL is $1.5K."
    assert len(llm_client.messages) == 1


@pytest.mark.asyncio
async def test_bot_query_service_routes_show_mantle_tvl_7d_to_metric_history_without_llm_parser(
    session_factory,
    seeded_data,
):
    llm_client = RejectIntentParseLLMClient("Mantle TVL rose over the last 7 days.")
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("show mantle tvl 7d", now=seeded_data)

    assert result["intent"] == "metric_history"
    assert result["data"]["metric_name"] == "tvl"
    assert result["answer"] == "Mantle TVL rose over the last 7 days."
    assert len(llm_client.messages) == 1


@pytest.mark.asyncio
async def test_bot_query_service_normalizes_llm_metric_latest_payload_before_dispatch(
    session_factory,
    seeded_data,
):
    llm_client = FakeLLMClient(
        [
            '{"intent":"metric_latest","entity":"Mantle","metric_name":"TVL"}',
            "Mantle TVL is $1.5K.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("what is Mantle TVL", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert result["data"]["entity"] == "mantle"
    assert result["data"]["metric_name"] == "tvl"
    assert result["answer"] == "Mantle TVL is $1.5K."


@pytest.mark.asyncio
async def test_bot_query_service_normalizes_llm_metric_alias_before_dispatch(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"metric_latest","entity":"Mantle","metric_name":"DEX volume"}',
            "Mantle DEX volume is $300.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("what is Mantle DEX volume", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert result["data"]["entity"] == "mantle"
    assert result["data"]["metric_name"] == "dex_volume"
    assert result["answer"] == "Mantle DEX volume is $300."


@pytest.mark.asyncio
async def test_bot_query_service_parser_prompt_includes_metric_catalog_constraints(
    session_factory,
    seeded_data,
):
    llm_client = FakeLLMClient(
        [
            '{"intent":"metric_latest","entity":"mantle","metric_name":"tvl"}',
            "Mantle TVL is $1.5K.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    await service.handle_message("what is mantle tvl", now=seeded_data)

    parser_prompt = llm_client.messages[0]
    assert "metric_latest" in parser_prompt[0]["content"]
    assert "metric_history" in parser_prompt[0]["content"]
    assert "tvl" in parser_prompt[0]["content"]
    assert "dex_volume" in parser_prompt[0]["content"]
    assert "mantle" in parser_prompt[0]["content"]
    assert "bare metric request defaults to metric_latest" in parser_prompt[0]["content"]


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
                AlertEvent(
                    scope="core",
                    entity="methlab",
                    metric_name="users",
                    current_value=Decimal("120"),
                    previous_value=Decimal("100"),
                    formatted_value="120",
                    time_window="1d",
                    change_pct=Decimal("0.20"),
                    severity="moderate",
                    trigger_reason="users up 20% in 1d",
                    source_platform="growthepie",
                    source_ref="https://api.growthepie.com",
                    detected_at=now - timedelta(hours=1),
                    is_ath=False,
                    is_milestone=False,
                    milestone_label=None,
                    cooldown_until=None,
                    reviewed=True,
                    ai_eligible=False,
                    created_at=now,
                ),
                WatchlistProtocol(
                    slug="aave-v3",
                    display_name="Aave V3",
                    category="lending",
                    monitoring_tier="special",
                    is_pinned=True,
                    metrics=["tvl", "supply", "borrowed", "utilization"],
                    active=True,
                    added_at=now,
                    updated_at=now,
                ),
                WatchlistProtocol(
                    slug="merchant-moe-dex",
                    display_name="Merchant Moe",
                    category="dexes",
                    monitoring_tier="dex",
                    is_pinned=False,
                    metrics=["tvl", "volume"],
                    active=True,
                    added_at=now,
                    updated_at=now,
                ),
                SourceRun(
                    source_platform="defillama",
                    job_name="core_defillama",
                    status="success",
                    records_collected=3,
                    started_at=now - timedelta(minutes=10),
                    completed_at=now - timedelta(minutes=9),
                    created_at=now,
                ),
                SourceRun(
                    source_platform="l2beat",
                    job_name="source_health",
                    status="failed",
                    records_collected=0,
                    error_message="timeout",
                    started_at=now - timedelta(minutes=8),
                    completed_at=now - timedelta(minutes=8),
                    created_at=now,
                ),
            ]
        )
        await session.commit()
    return now


@pytest.mark.asyncio
async def test_bot_query_service_handles_latest_metric_question(session_factory, seeded_data):
    llm_client = RejectIntentParseLLMClient("Mantle TVL is $1.5K.")
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot mantle tvl latest", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert result["answer"] == "Mantle TVL is $1.5K."
    assert result["data"]["metric_name"] == "tvl"
    assert "https://defillama.com/chain/Mantle" in result["source_urls"]
    assert result["card"]["header"]["title"]["content"] == "Query Result"


@pytest.mark.asyncio
async def test_bot_query_service_handles_metric_history_question(session_factory, seeded_data):
    llm_client = RejectIntentParseLLMClient("Mantle TVL rose over the last 7 days.")
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
async def test_bot_query_service_handles_alerts_list_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"alerts_list","entity":"mantle","severity":"high","days":7,"limit":5}',
            "There is one high-severity Mantle alert in the last 7 days.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot show mantle high alerts", now=seeded_data)

    assert result["intent"] == "alerts_list"
    assert result["answer"] == "There is one high-severity Mantle alert in the last 7 days."
    assert result["data"]["total"] == 1
    assert result["data"]["alerts"][0]["entity"] == "mantle"


@pytest.mark.asyncio
async def test_bot_query_service_handles_health_status_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"health_status"}',
            "System health is degraded because one source is currently failing.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot system health", now=seeded_data)

    assert result["intent"] == "health_status"
    assert result["answer"] == "System health is degraded because one source is currently failing."
    assert result["data"]["status"] == "degraded"
    assert result["data"]["last_source_runs"]["l2beat"]["status"] == "failed"


@pytest.mark.asyncio
async def test_bot_query_service_handles_source_health_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"source_health","source_platform":"defillama","limit":5}',
            "DefiLlama most recently reported a successful run.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot source health defillama", now=seeded_data)

    assert result["intent"] == "source_health"
    assert result["answer"] == "DefiLlama most recently reported a successful run."
    assert result["data"]["runs"][0]["source_platform"] == "defillama"
    assert result["data"]["runs"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_bot_query_service_handles_watchlist_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"watchlist"}',
            "The watchlist currently includes Aave V3 and Merchant Moe.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot show watchlist", now=seeded_data)

    assert result["intent"] == "watchlist"
    assert result["answer"] == "The watchlist currently includes Aave V3 and Merchant Moe."
    assert [protocol["slug"] for protocol in result["data"]["protocols"]] == [
        "aave-v3",
        "merchant-moe-dex",
    ]


@pytest.mark.asyncio
async def test_bot_query_service_handles_daily_summary_question(session_factory, seeded_data):
    llm_client = FakeLLMClient(
        [
            '{"intent":"daily_summary","days_ago":0}',
            "On 2026-03-15, Mantle TVL and DEX activity were recorded alongside a high-severity alert.",
        ]
    )
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot daily summary today", now=seeded_data)

    assert result["intent"] == "daily_summary"
    assert result["answer"] == (
        "On 2026-03-15, Mantle TVL and DEX activity were recorded alongside a high-severity alert."
    )
    assert result["data"]["day"] == "2026-03-15"
    assert {metric["metric_name"] for metric in result["data"]["metrics"]} == {"tvl", "dex_volume"}


@pytest.mark.asyncio
async def test_bot_query_service_returns_supported_query_fallback_for_unsupported_prompt(
    session_factory,
    seeded_data,
):
    llm_client = FakeLLMClient(['{"intent":"web_search","query":"mantle latest news"}'])
    service = BotQueryService(session_factory=ForbiddenSessionFactory(), llm_client=llm_client)

    result = await service.handle_message("@bot tell me a joke", now=seeded_data)

    assert result["intent"] == "unsupported"
    assert "latest metrics" in result["answer"].lower()
    assert "metric history" in result["answer"].lower()
    assert "external actions" not in result["answer"].lower()
    assert result["source_urls"] == []
    assert len(llm_client.messages) == 1


@pytest.mark.asyncio
async def test_bot_query_service_returns_constrained_explanation_when_supported_query_has_no_internal_data(
    session_factory,
    seeded_data,
):
    llm_client = FakeLLMClient(['{"intent":"metric_latest","entity":"unknown","metric_name":"tvl"}'])
    service = BotQueryService(session_factory=session_factory, llm_client=llm_client)

    result = await service.handle_message("@bot latest unknown tvl", now=seeded_data)

    assert result["intent"] == "metric_latest"
    assert "could not find internal monitoring data" in result["answer"].lower()
    assert "external actions" not in result["answer"].lower()
    assert result["data"] == {}
    assert result["source_urls"] == []
    assert len(llm_client.messages) == 1


@pytest.mark.asyncio
async def test_bot_query_service_keeps_mutation_style_requests_unsupported(session_factory, seeded_data):
    llm_client = FakeLLMClient(['{"intent":"watchlist_refresh"}'])
    service = BotQueryService(session_factory=ForbiddenSessionFactory(), llm_client=llm_client)

    result = await service.handle_message("@bot refresh watchlist", now=seeded_data)

    assert result["intent"] == "unsupported"
    assert "read-only mantle monitoring queries" in result["answer"].lower()
    assert "external actions" not in result["answer"].lower()
    assert result["data"] == {}
    assert len(llm_client.messages) == 1
