import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.deps import get_db_session
from src.db.models import AlertEvent, Base, MetricSnapshot, WatchlistProtocol
from src.main import create_app


@pytest.fixture()
def test_db(tmp_path):
    db_path = tmp_path / "api_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return engine


@pytest.fixture()
async def session_factory(test_db):
    async with test_db.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_db, expire_on_commit=False)
    yield factory
    await test_db.dispose()


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.router.lifespan_context = _null_lifespan

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    return TestClient(app)


from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def _null_lifespan(app: FastAPI):
    yield


@pytest.fixture()
async def seeded_alerts(session_factory):
    now = datetime.now(tz=timezone.utc)
    async with session_factory() as session:
        for i in range(3):
            session.add(AlertEvent(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                current_value=Decimal("1600000000") + i * 100_000_000,
                time_window="7d",
                severity=["moderate", "high", "critical"][i],
                trigger_reason=f"threshold_{15 + i * 5}pct_7d",
                detected_at=now - timedelta(hours=i),
                is_ath=i == 2,
                is_milestone=False,
                reviewed=False,
                ai_eligible=False,
                created_at=now,
            ))
        await session.commit()


@pytest.fixture()
async def seeded_snapshots(session_factory):
    now = datetime.now(tz=timezone.utc)
    async with session_factory() as session:
        for i in range(5):
            session.add(MetricSnapshot(
                scope="core",
                entity="mantle",
                metric_name="tvl",
                value=Decimal("1400000000") + i * 50_000_000,
                unit="usd",
                source_platform="defillama",
                collected_at=now - timedelta(days=5 - i),
                created_at=now,
            ))
        await session.commit()


@pytest.fixture()
async def seeded_watchlist(session_factory):
    async with session_factory() as session:
        session.add(WatchlistProtocol(
            slug="aave-v3",
            display_name="Aave V3",
            category="lending",
            monitoring_tier="special",
            is_pinned=True,
            metrics=json.dumps(["tvl", "supply", "borrowed", "utilization"]),
            active=True,
            added_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        ))
        await session.commit()
