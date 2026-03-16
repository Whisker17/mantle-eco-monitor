from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BotCatalog:
    intents: tuple[str, ...]
    entity_aliases: dict[str, str]
    metric_aliases: dict[str, str]
    tools: list[dict[str, Any]]


def build_bot_catalog() -> BotCatalog:
    canonical_entities = ["mantle"]
    canonical_metrics = ["dex_volume", "tvl"]
    return BotCatalog(
        intents=(
            "metric_latest",
            "metric_history",
            "recent_alerts",
            "alerts_list",
            "health_status",
            "source_health",
            "watchlist",
            "daily_summary",
        ),
        entity_aliases={
            "mantle": "mantle",
            "Mantle": "mantle",
            "MANTLE": "mantle",
        },
        metric_aliases={
            "tvl": "tvl",
            "TVL": "tvl",
            "dex volume": "dex_volume",
            "DEX volume": "dex_volume",
            "dex_volume": "dex_volume",
        },
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "metric_latest",
                    "description": "Get the latest value of a Mantle metric.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "enum": canonical_entities},
                            "metric_name": {"type": "string", "enum": canonical_metrics},
                        },
                        "required": ["entity", "metric_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "metric_history",
                    "description": "Get metric history for a Mantle metric over a day window.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "enum": canonical_entities},
                            "metric_name": {"type": "string", "enum": canonical_metrics},
                            "days": {"type": "integer", "minimum": 1, "maximum": 90},
                        },
                        "required": ["entity", "metric_name", "days"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recent_alerts",
                    "description": "Get recent alerts, optionally filtered by entity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "alerts_list",
                    "description": "List alerts with optional filters.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "scope": {"type": "string"},
                            "severity": {"type": "string"},
                            "is_ath": {"type": "boolean"},
                            "is_milestone": {"type": "boolean"},
                            "reviewed": {"type": "boolean"},
                            "days": {"type": "integer", "minimum": 1, "maximum": 90},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                            "offset": {"type": "integer", "minimum": 0},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "health_status",
                    "description": "Get overall service health status.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "source_health",
                    "description": "Get recent source health runs, optionally filtered by source.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_platform": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "watchlist",
                    "description": "Get the current monitoring watchlist.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "daily_summary",
                    "description": "Get the daily summary context for a specific day.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "string"},
                            "days_ago": {"type": "integer", "minimum": 0, "maximum": 30},
                        },
                    },
                },
            },
        ],
    )
