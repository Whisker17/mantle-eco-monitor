from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotCatalog:
    intents: tuple[str, ...]
    entity_aliases: dict[str, str]
    metric_aliases: dict[str, str]


def build_bot_catalog() -> BotCatalog:
    return BotCatalog(
        intents=(
            "metric_latest",
            "metric_history",
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
    )
