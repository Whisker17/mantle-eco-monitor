from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.db.models import Base, AlertEvent
from src.rules.cooldown import apply_cooldown
from src.rules.engine import AlertCandidate


@pytest.fixture()
async def async_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_candidate(
    severity="moderate",
    trigger_reason="threshold_15pct_7d",
    entity="mantle",
    metric_name="tvl",
) -> AlertCandidate:
    return AlertCandidate(
        scope="core",
        entity=entity,
        metric_name=metric_name,
        current_value=Decimal("1600000000"),
        previous_value=Decimal("1400000000"),
        formatted_value=None,
        time_window="7d",
        change_pct=Decimal("0.1428"),
        severity=severity,
        trigger_reason=trigger_reason,
    )


@pytest.mark.asyncio
async def test_cooldown_allows_first_alert(async_session):
    candidates = [_make_candidate()]
    result = await apply_cooldown(candidates, async_session)
    assert len(result) == 1
    assert result[0].cooldown_until is not None


@pytest.mark.asyncio
async def test_cooldown_suppresses_duplicate_alert(async_session):
    now = datetime.now(tz=timezone.utc)
    existing = AlertEvent(
        scope="core",
        entity="mantle",
        metric_name="tvl",
        current_value=Decimal("1500000000"),
        time_window="7d",
        severity="moderate",
        trigger_reason="threshold_15pct_7d",
        detected_at=now - timedelta(hours=1),
        cooldown_until=now + timedelta(hours=47),
        is_ath=False,
        is_milestone=False,
        reviewed=False,
        ai_eligible=False,
        created_at=now - timedelta(hours=1),
    )
    async_session.add(existing)
    await async_session.commit()

    candidates = [_make_candidate()]
    result = await apply_cooldown(candidates, async_session)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_cooldown_allows_after_expiry(async_session):
    now = datetime.now(tz=timezone.utc)
    existing = AlertEvent(
        scope="core",
        entity="mantle",
        metric_name="tvl",
        current_value=Decimal("1500000000"),
        time_window="7d",
        severity="moderate",
        trigger_reason="threshold_15pct_7d",
        detected_at=now - timedelta(hours=50),
        cooldown_until=now - timedelta(hours=2),
        is_ath=False,
        is_milestone=False,
        reviewed=False,
        ai_eligible=False,
        created_at=now - timedelta(hours=50),
    )
    async_session.add(existing)
    await async_session.commit()

    candidates = [_make_candidate()]
    result = await apply_cooldown(candidates, async_session)
    assert len(result) == 1
