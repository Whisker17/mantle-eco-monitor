from src.protocols.aave import AaveAdapter
from src.protocols.dex import DexAdapter
from src.protocols.generic import GenericAdapter
from src.protocols.registry import get_adapter


def test_registry_returns_aave_adapter_for_special_slug():
    assert isinstance(get_adapter("aave-v3", "special"), AaveAdapter)


def test_registry_returns_dex_adapter_for_dex_tier():
    assert isinstance(get_adapter("merchant-moe-dex", "dex"), DexAdapter)


def test_registry_returns_generic_adapter_for_non_dex_protocols():
    assert isinstance(get_adapter("ondo-yield-assets", "generic"), GenericAdapter)


def test_registry_returns_aggregate_adapter_for_curated_aggregate_slugs():
    aggregate = get_adapter("merchant-moe", "dex")
    assert aggregate.__class__.__name__ == "AggregateAdapter"
    assert get_adapter("stargate-finance", "generic").__class__.__name__ == "AggregateAdapter"
    assert get_adapter("woofi", "dex").__class__.__name__ == "AggregateAdapter"
