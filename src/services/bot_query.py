from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from src.integrations.lark.cards import build_bot_reply_card
from src.services.query_tools import get_latest_metric, get_metric_history, get_recent_alerts

UNSUPPORTED_MESSAGE = (
    "I currently support latest metrics, history, recent alerts, daily summaries, and source lookups."
)


class BotQueryService:
    def __init__(self, *, session_factory, llm_client):
        self._session_factory = session_factory
        self._llm_client = llm_client

    async def handle_message(self, text: str, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(tz=UTC)
        intent_payload = await self._parse_intent(text)
        if intent_payload["intent"] == "unsupported":
            return self._unsupported_response()

        data = await self._execute_intent(intent_payload, now=now)
        if data is None:
            return self._unsupported_response()

        source_urls = sorted(self._collect_source_urls(data))
        answer = await self._llm_client.complete(
            [
                {
                    "role": "system",
                    "content": "Answer the user's Mantle monitoring question using only the supplied JSON data.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "intent": intent_payload["intent"],
                            "question": text,
                            "data": data,
                            "source_urls": source_urls,
                        },
                        sort_keys=True,
                    ),
                },
            ]
        )
        return {
            "intent": intent_payload["intent"],
            "answer": answer,
            "data": data,
            "source_urls": source_urls,
            "card": build_bot_reply_card(answer=answer, source_urls=source_urls),
        }

    async def _parse_intent(self, text: str) -> dict[str, Any]:
        response = await self._llm_client.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Map the user message to JSON with intent one of: "
                        "metric_latest, metric_history, recent_alerts, unsupported."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ]
        )
        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            return {"intent": "unsupported"}

        return self._validate_intent(payload)

    def _validate_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = payload.get("intent")
        if intent == "metric_latest":
            if isinstance(payload.get("entity"), str) and isinstance(payload.get("metric_name"), str):
                return {
                    "intent": intent,
                    "entity": payload["entity"],
                    "metric_name": payload["metric_name"],
                }
        if intent == "metric_history":
            if (
                isinstance(payload.get("entity"), str)
                and isinstance(payload.get("metric_name"), str)
                and isinstance(payload.get("days"), int)
                and payload["days"] > 0
            ):
                return {
                    "intent": intent,
                    "entity": payload["entity"],
                    "metric_name": payload["metric_name"],
                    "days": payload["days"],
                }
        if intent == "recent_alerts":
            entity = payload.get("entity")
            limit = payload.get("limit", 5)
            if (entity is None or isinstance(entity, str)) and isinstance(limit, int) and limit > 0:
                return {
                    "intent": intent,
                    "entity": entity,
                    "limit": limit,
                }
        return {"intent": "unsupported"}

    async def _execute_intent(self, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            match payload["intent"]:
                case "metric_latest":
                    return await get_latest_metric(
                        session,
                        entity=payload["entity"],
                        metric_name=payload["metric_name"],
                    )
                case "metric_history":
                    return await get_metric_history(
                        session,
                        entity=payload["entity"],
                        metric_name=payload["metric_name"],
                        since=now - timedelta(days=payload["days"]),
                        until=now,
                    )
                case "recent_alerts":
                    return await get_recent_alerts(
                        session,
                        entity=payload.get("entity"),
                        limit=payload["limit"],
                    )
                case _:
                    return None

    def _collect_source_urls(self, value: Any) -> set[str]:
        urls: set[str] = set()
        if isinstance(value, dict):
            source_ref = value.get("source_ref")
            if isinstance(source_ref, str) and source_ref:
                urls.add(source_ref)
            for nested in value.values():
                urls.update(self._collect_source_urls(nested))
        elif isinstance(value, list):
            for item in value:
                urls.update(self._collect_source_urls(item))
        return urls

    def _unsupported_response(self) -> dict[str, Any]:
        return {
            "intent": "unsupported",
            "answer": UNSUPPORTED_MESSAGE,
            "data": {},
            "source_urls": [],
            "card": build_bot_reply_card(answer=UNSUPPORTED_MESSAGE, source_urls=[]),
        }
