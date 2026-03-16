from __future__ import annotations

import argparse
import asyncio
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.db.engine import build_engine, build_session_factory


def load_settings() -> Settings:
    return Settings()


def build_admin_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    settings = settings or load_settings()
    engine = build_engine(settings)
    return build_session_factory(engine)


async def run_async_handler(
    handler: Callable[[argparse.Namespace], Awaitable[int]],
    args: argparse.Namespace,
) -> int:
    return await handler(args)


def run_handler(
    handler: Callable[[argparse.Namespace], Awaitable[int]],
    args: argparse.Namespace,
) -> int:
    return asyncio.run(run_async_handler(handler, args))
