import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.deps import get_db_session
from src.db.models import Base, MetricSnapshot
from src.main import create_app


@pytest.fixture()
async def test_engine(tmp_path):
    db_path = tmp_path / "integration_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture()
async def test_session(test_session_factory):
    async with test_session_factory() as session:
        yield session


@asynccontextmanager
async def _null_lifespan(app: FastAPI):
    yield


@pytest.fixture()
def test_app(test_session_factory):
    app = create_app()
    app.router.lifespan_context = _null_lifespan

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    return TestClient(app)
