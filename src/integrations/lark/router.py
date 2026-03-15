from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from src.api.deps import get_db_session, get_session_factory
from src.db.repositories import (
    create_delivery_event,
    get_delivery_event_by_logical_key,
    mark_delivery_event_delivered,
    mark_delivery_event_failed,
)
from src.integrations.lark.client import LarkClient
from src.integrations.lark.signature import verify_callback_token
from src.services.bot_query import BotQueryService
from src.services.llm import LLMClient

lark_router = APIRouter()


def _build_bot_query_service(settings: Settings):
    return BotQueryService(
        session_factory=get_session_factory(settings),
        llm_client=LLMClient(
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            app_name=settings.llm_app_name,
            app_url=settings.llm_app_url,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        external_actions_enabled=settings.bot_external_actions_enabled,
    )


def _build_lark_client(settings: Settings):
    return LarkClient(
        app_id=settings.lark_app_id,
        app_secret=settings.lark_app_secret,
    )


def _extract_token(payload: dict[str, Any]) -> str | None:
    header = payload.get("header")
    if isinstance(header, dict):
        token = header.get("token")
        if isinstance(token, str):
            return token
    token = payload.get("token")
    if isinstance(token, str):
        return token
    return None


def _extract_message_text(payload: dict[str, Any]) -> str:
    event = payload.get("event", {})
    message = event.get("message", {})
    if message.get("message_type") != "text":
        raise HTTPException(status_code=400, detail="Unsupported message type")
    content = json.loads(message["content"])
    text = content.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Missing message text")
    return text


@lark_router.post("/api/integrations/lark/events")
async def handle_lark_event(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
):
    settings = Settings()
    token = _extract_token(payload)
    if not verify_callback_token(token, settings.lark_verification_token):
        raise HTTPException(status_code=401, detail="Invalid verification token")

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(status_code=400, detail="Missing challenge")
        return {"challenge": challenge}

    if not settings.lark_bot_enabled:
        raise HTTPException(status_code=503, detail="Lark bot is disabled")

    header = payload.get("header", {})
    event_id = header.get("event_id")
    if not isinstance(event_id, str):
        raise HTTPException(status_code=400, detail="Missing event id")

    logical_key = f"{settings.lark_environment}:lark_event:callback:{event_id}"
    existing = await get_delivery_event_by_logical_key(session, logical_key)
    if existing is not None:
        return {"status": "ignored", "reason": "duplicate"}

    delivery = await create_delivery_event(
        session,
        channel="lark_event",
        entity_type="callback",
        entity_id=None,
        logical_key=logical_key,
        environment=settings.lark_environment,
        status="pending",
        attempt_count=0,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    await session.commit()

    bot_query_service = _build_bot_query_service(settings)
    lark_client = _build_lark_client(settings)

    try:
        text = _extract_message_text(payload)
        result = await bot_query_service.handle_message(text)
        message_id = payload["event"]["message"]["message_id"]
        await lark_client.reply_card(message_id=message_id, card=result["card"])
    except Exception as exc:
        await mark_delivery_event_failed(session, delivery, error=str(exc))
        await session.commit()
        raise

    await mark_delivery_event_delivered(
        session,
        delivery,
        delivered_at=datetime.now(tz=timezone.utc),
    )
    await session.commit()
    return {"status": "ok"}
