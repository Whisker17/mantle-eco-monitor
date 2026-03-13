from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import Settings

_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        if settings is None:
            settings = Settings()
        engine = create_async_engine(settings.database_url, echo=False)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session
