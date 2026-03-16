from __future__ import annotations

from src.protocols.aave import AaveAdapter
from src.protocols.aggregate import AggregateAdapter
from src.protocols.base import ProtocolAdapter
from src.protocols.dex import DexAdapter
from src.protocols.generic import GenericAdapter


AGGREGATE_PROTOCOLS: dict[str, dict[str, object]] = {
    "merchant-moe": {
        "tvl_slugs": ["merchant-moe-dex", "merchant-moe-liquidity-book"],
        "volume_slugs": ["merchant-moe-dex", "merchant-moe-liquidity-book"],
        "tier": "dex",
    },
    "stargate-finance": {
        "tvl_slugs": ["stargate-v1", "stargate-v2"],
        "volume_slugs": [],
        "tier": "generic",
    },
    "woofi": {
        "tvl_slugs": ["woofi-swap", "woofi-earn"],
        "volume_slugs": ["woofi-swap"],
        "tier": "dex",
    },
}


def get_adapter(slug: str, tier: str) -> ProtocolAdapter:
    if slug == "aave-v3":
        return AaveAdapter()
    if slug in AGGREGATE_PROTOCOLS:
        config = AGGREGATE_PROTOCOLS[slug]
        return AggregateAdapter(
            slug=slug,
            monitoring_tier=str(config["tier"]),
            tvl_slugs=list(config["tvl_slugs"]),
            volume_slugs=list(config["volume_slugs"]),
        )
    if tier == "dex":
        return DexAdapter(slug)
    return GenericAdapter(slug)
