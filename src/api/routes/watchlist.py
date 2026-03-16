from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas import WatchlistItemResponse, WatchlistResponse
from src.db.models import WatchlistProtocol

watchlist_router = APIRouter()
logger = logging.getLogger(__name__)


@watchlist_router.get("/api/watchlist", response_model=WatchlistResponse)
async def get_watchlist(
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(WatchlistProtocol)
        .where(WatchlistProtocol.active == True)
        .order_by(WatchlistProtocol.is_pinned.desc(), WatchlistProtocol.slug)
    )
    protocols = result.scalars().all()

    return WatchlistResponse(
        protocols=[
            WatchlistItemResponse(
                id=p.id,
                slug=p.slug,
                display_name=p.display_name,
                category=p.category,
                monitoring_tier=p.monitoring_tier,
                is_pinned=p.is_pinned,
                metrics=p.metrics,
                active=p.active,
            )
            for p in protocols
        ]
    )


@watchlist_router.post("/api/watchlist/refresh")
async def refresh_watchlist(
    session: AsyncSession = Depends(get_db_session),
):
    from src.db.repositories import upsert_watchlist
    from src.protocols.watchlist import WatchlistManager

    manager = WatchlistManager()
    entries = manager.get_seed()

    await upsert_watchlist(session, entries)
    await session.commit()
    return {"status": "refreshed", "count": len(entries)}
