from __future__ import annotations

from src.protocols.aave import AaveAdapter
from src.protocols.base import ProtocolAdapter
from src.protocols.dex import DexAdapter
from src.protocols.generic import GenericAdapter


def get_adapter(slug: str, tier: str) -> ProtocolAdapter:
    if slug == "aave-v3":
        return AaveAdapter()
    if tier == "dex":
        return DexAdapter(slug)
    return GenericAdapter(slug)
