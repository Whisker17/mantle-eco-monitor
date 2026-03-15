from __future__ import annotations

import threading

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import Settings

_session_factories: dict[int, async_sessionmaker[AsyncSession]] = {}


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    thread_id = threading.get_ident()
    session_factory = _session_factories.get(thread_id)
    if session_factory is None:
        if settings is None:
            settings = Settings()
        engine = create_async_engine(settings.database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        _session_factories[thread_id] = session_factory
    return session_factory


async def get_db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session
