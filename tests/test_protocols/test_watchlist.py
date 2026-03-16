from src.protocols.watchlist import WatchlistManager, _score_protocol


def test_watchlist_manager_returns_fixed_curated_protocols():
    manager = WatchlistManager()
    watchlist = manager.build_watchlist([])

    assert [entry["slug"] for entry in watchlist] == [
        "aave-v3",
        "cian-yield-layer",
        "mantle-index-four-fund",
        "merchant-moe",
        "treehouse-protocol",
        "ondo-yield-assets",
        "agni-finance",
        "stargate-finance",
        "apex-omni",
        "compound-v3",
        "uniswap-v3",
        "init-capital",
        "woofi",
        "fluxion-network",
    ]
    assert next(w for w in watchlist if w["slug"] == "aave-v3")["pinned"] is True


def test_watchlist_excludes_cex():
    manager = WatchlistManager()

    protocols = [
        {"slug": "binance", "name": "Binance", "category": "CEX", "tvl": 1_000_000_000},
        {"slug": "some-dex", "name": "Some DEX", "category": "Dexes", "tvl": 10_000_000},
    ]

    ranked = manager.score_and_rank(protocols)
    slugs = [p["slug"] for p in ranked]
    assert "binance" not in slugs
    assert "some-dex" in slugs


def test_score_protocol_dex_beats_bridge():
    dex_score = _score_protocol(50_000_000, "dex")
    bridge_score = _score_protocol(100_000_000, "bridge")
    assert dex_score > bridge_score


def test_watchlist_seed_contains_aave():
    manager = WatchlistManager()
    seed = manager.get_seed()
    slugs = [s["slug"] for s in seed]
    assert "aave-v3" in slugs


def test_fixed_watchlist_ignores_ranked_protocols():
    manager = WatchlistManager()

    ranked = manager.score_and_rank(
        [
            {"slug": "random-proto", "name": "Random Proto", "category": "Dexes", "tvl": 999_999_999},
        ]
    )
    watchlist = manager.build_watchlist(ranked)

    assert "random-proto" not in [w["slug"] for w in watchlist]
