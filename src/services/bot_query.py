from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.integrations.lark.cards import build_bot_reply_card
from src.services.bot_catalog import build_bot_catalog
from src.services.query_tools import (
    get_alerts_list,
    get_daily_summary_context,
    get_health_status,
    get_latest_metric,
    get_metric_history,
    get_recent_alerts,
    get_source_health,
    get_watchlist,
)

SUPPORTED_INTENTS = (
    "metric_latest",
    "metric_history",
    "recent_alerts",
    "alerts_list",
    "health_status",
    "source_health",
    "watchlist",
    "daily_summary",
)
SUPPORTED_CAPABILITIES_TEXT = (
    "latest metrics, metric history, alerts, health status, source health, watchlist, "
    "and daily summaries"
)

logger = logging.getLogger(__name__)


class BotQueryService:
    def __init__(self, *, session_factory, llm_client, external_actions_enabled: bool = False):
        self._session_factory = session_factory
        self._llm_client = llm_client
        self._external_actions_enabled = external_actions_enabled
        self._catalog = build_bot_catalog()
        self._intent_handlers = {
            "metric_latest": self._handle_metric_latest,
            "metric_history": self._handle_metric_history,
            "recent_alerts": self._handle_recent_alerts,
            "alerts_list": self._handle_alerts_list,
            "health_status": self._handle_health_status,
            "source_health": self._handle_source_health,
            "watchlist": self._handle_watchlist,
            "daily_summary": self._handle_daily_summary,
        }

    async def handle_message(self, text: str, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(tz=UTC)
        intent_payload = await self._parse_intent(text)
        if intent_payload["intent"] == "unsupported":
            return await self._build_constrained_response(
                text=text,
                requested_intent=intent_payload.get("requested_intent"),
                reason="unsupported_intent",
            )

        data = await self._execute_intent(intent_payload, now=now)
        if not self._has_internal_data(intent_payload["intent"], data):
            return await self._build_constrained_response(
                text=text,
                requested_intent=intent_payload["intent"],
                reason="no_internal_data",
            )

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
        deterministic_payload = self._parse_metric_intent_deterministically(text)
        if deterministic_payload is not None:
            logger.debug("Bot query parser path=deterministic payload=%s", deterministic_payload)
            return deterministic_payload

        parser_messages = self._build_tool_call_messages(text)
        logger.debug("Bot query parser path=tool_call question=%s", text)
        tool_result = await self._llm_client.complete_with_tools(
            parser_messages,
            tools=self._catalog.tools,
            tool_choice="auto",
        )
        if tool_result is None:
            logger.debug("Bot query parser path=tool_call result=none")
            return {"intent": "unsupported"}

        logger.debug("Bot query parser raw_tool_call=%s", tool_result.raw_tool_call)
        payload = {"intent": tool_result.tool_name, **tool_result.arguments}
        validated = self._validate_intent(payload)
        logger.debug("Bot query parser validated_payload=%s", validated)
        return validated

    def _parse_metric_intent_deterministically(self, text: str) -> dict[str, Any] | None:
        normalized = self._normalize_query_text(text)
        if not normalized:
            return None

        tokens = normalized.split()
        if not tokens:
            return None

        if tokens[:2] in (["what", "is"], ["what", "s"]):
            tokens = tokens[2:]
        elif tokens and tokens[0] == "whats":
            tokens = tokens[1:]
        if tokens and tokens[0] in {"query", "show", "get", "check", "current", "latest"}:
            tokens = tokens[1:]
        if tokens and tokens[0] == "the":
            tokens = tokens[1:]
        if len(tokens) < 2:
            return None

        days = None
        if re.fullmatch(r"\d+d", tokens[-1]):
            days = int(tokens[-1][:-1])
            tokens = tokens[:-1]
        elif tokens[-1] == "latest":
            tokens = tokens[:-1]

        if len(tokens) < 2:
            return None

        entity = self._lookup_alias(tokens[0], self._catalog.entity_aliases)
        if entity is None:
            return None

        metric_name = self._lookup_alias(" ".join(tokens[1:]), self._catalog.metric_aliases)
        if metric_name is None:
            return None

        if days is not None:
            return {
                "intent": "metric_history",
                "entity": entity,
                "metric_name": metric_name,
                "days": days,
            }
        return {
            "intent": "metric_latest",
            "entity": entity,
            "metric_name": metric_name,
        }

    def _normalize_query_text(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^@bot\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("_", " ")
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.lower().strip()

    def _lookup_alias(self, value: str, aliases: dict[str, str]) -> str | None:
        if value in aliases:
            return aliases[value]
        return aliases.get(value.lower())

    def _build_tool_call_messages(self, text: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Choose the best internal read-only Mantle monitoring tool for the user request. "
                    "Only use a tool when the request matches one of the supported read-only queries. "
                    "If the request is unrelated, unsupported, or asks for mutation or external actions, do not call a tool."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ]

    def _normalize_metric_payload(self, payload: dict[str, Any]) -> dict[str, str] | None:
        entity = payload.get("entity")
        metric_name = payload.get("metric_name")
        if not isinstance(entity, str) or not isinstance(metric_name, str):
            return None

        normalized_entity = re.sub(r"\s+", " ", entity.strip().lower())
        normalized_metric_name = re.sub(r"\s+", "_", metric_name.strip().lower())
        canonical_entity = self._lookup_alias(entity.strip(), self._catalog.entity_aliases) or normalized_entity
        canonical_metric_name = (
            self._lookup_alias(metric_name.strip(), self._catalog.metric_aliases) or normalized_metric_name
        )

        return {
            "entity": canonical_entity,
            "metric_name": canonical_metric_name,
        }

    def _validate_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = payload.get("intent")
        if intent == "metric_latest":
            normalized = self._normalize_metric_payload(payload)
            if normalized is not None:
                return {
                    "intent": intent,
                    "entity": normalized["entity"],
                    "metric_name": normalized["metric_name"],
                }
        if intent == "metric_history":
            normalized = self._normalize_metric_payload(payload)
            if normalized is not None and isinstance(payload.get("days"), int) and payload["days"] > 0:
                return {
                    "intent": intent,
                    "entity": normalized["entity"],
                    "metric_name": normalized["metric_name"],
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
        if intent == "alerts_list":
            entity = payload.get("entity")
            scope = payload.get("scope")
            severity = payload.get("severity")
            is_ath = payload.get("is_ath")
            is_milestone = payload.get("is_milestone")
            reviewed = payload.get("reviewed")
            days = payload.get("days", 7)
            limit = payload.get("limit", 10)
            offset = payload.get("offset", 0)
            if (
                (entity is None or isinstance(entity, str))
                and (scope is None or isinstance(scope, str))
                and (severity is None or isinstance(severity, str))
                and (is_ath is None or isinstance(is_ath, bool))
                and (is_milestone is None or isinstance(is_milestone, bool))
                and (reviewed is None or isinstance(reviewed, bool))
                and isinstance(days, int)
                and days > 0
                and isinstance(limit, int)
                and limit > 0
                and isinstance(offset, int)
                and offset >= 0
            ):
                return {
                    "intent": intent,
                    "entity": entity,
                    "scope": scope,
                    "severity": severity,
                    "is_ath": is_ath,
                    "is_milestone": is_milestone,
                    "reviewed": reviewed,
                    "days": days,
                    "limit": limit,
                    "offset": offset,
                }
        if intent == "health_status":
            return {"intent": intent}
        if intent == "source_health":
            source_platform = payload.get("source_platform")
            limit = payload.get("limit", 20)
            if (source_platform is None or isinstance(source_platform, str)) and isinstance(limit, int) and limit > 0:
                return {
                    "intent": intent,
                    "source_platform": source_platform,
                    "limit": limit,
                }
        if intent == "watchlist":
            return {"intent": intent}
        if intent == "daily_summary":
            if isinstance(payload.get("day"), str):
                try:
                    date.fromisoformat(payload["day"])
                except ValueError:
                    return {"intent": "unsupported", "requested_intent": intent}
                return {"intent": intent, "day": payload["day"]}
            days_ago = payload.get("days_ago", 1)
            if isinstance(days_ago, int) and days_ago >= 0:
                return {"intent": intent, "days_ago": days_ago}
        if isinstance(intent, str):
            return {"intent": "unsupported", "requested_intent": intent}
        return {"intent": "unsupported", "requested_intent": None}

    async def _execute_intent(self, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
        handler = self._intent_handlers.get(payload["intent"])
        if handler is None:
            return None

        async with self._session_factory() as session:
            return await handler(session, payload, now=now)

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

    async def _handle_metric_latest(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
        return await get_latest_metric(
            session,
            entity=payload["entity"],
            metric_name=payload["metric_name"],
        )

    async def _handle_metric_history(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_metric_history(
            session,
            entity=payload["entity"],
            metric_name=payload["metric_name"],
            since=now - timedelta(days=payload["days"]),
            until=now,
        )

    async def _handle_recent_alerts(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_recent_alerts(
            session,
            entity=payload.get("entity"),
            limit=payload["limit"],
        )

    async def _handle_alerts_list(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_alerts_list(
            session,
            scope=payload.get("scope"),
            entity=payload.get("entity"),
            severity=payload.get("severity"),
            is_ath=payload.get("is_ath"),
            is_milestone=payload.get("is_milestone"),
            reviewed=payload.get("reviewed"),
            since=now - timedelta(days=payload["days"]),
            until=now,
            limit=payload["limit"],
            offset=payload["offset"],
        )

    async def _handle_health_status(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_health_status(session)

    async def _handle_source_health(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_source_health(
            session,
            source_platform=payload.get("source_platform"),
            limit=payload["limit"],
        )

    async def _handle_watchlist(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        return await get_watchlist(session)

    async def _handle_daily_summary(self, session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        if "day" in payload:
            summary_day = date.fromisoformat(payload["day"])
        else:
            summary_day = now.date() - timedelta(days=payload.get("days_ago", 1))
        return await get_daily_summary_context(session, day=summary_day)

    def _has_internal_data(self, intent: str, data: dict[str, Any] | None) -> bool:
        if data is None:
            return False

        if intent == "metric_history":
            return bool(data.get("points"))
        if intent == "alerts_list":
            return bool(data.get("alerts"))
        if intent == "recent_alerts":
            return bool(data.get("alerts"))
        if intent == "source_health":
            return bool(data.get("runs"))
        if intent == "watchlist":
            return bool(data.get("protocols"))
        if intent == "daily_summary":
            return bool(data.get("metrics")) or bool(data.get("alerts"))
        return True

    async def _build_constrained_response(
        self,
        *,
        text: str,
        requested_intent: str | None,
        reason: str,
    ) -> dict[str, Any]:
        if reason == "no_internal_data":
            answer = (
                "I could not find internal monitoring data for that query yet. "
                f"I can still help with {SUPPORTED_CAPABILITIES_TEXT} that exist in the system."
            )
        else:
            answer = (
                "I can only answer read-only Mantle monitoring queries. "
                f"Supported queries include {SUPPORTED_CAPABILITIES_TEXT}."
            )
        response_intent = "unsupported" if reason == "unsupported_intent" else requested_intent or "unsupported"
        return {
            "intent": response_intent,
            "answer": answer,
            "data": {},
            "source_urls": [],
            "card": build_bot_reply_card(answer=answer, source_urls=[]),
        }
