from src.protocols.watchlist import WatchlistManager, _score_protocol


def test_watchlist_manager_preserves_pinned_aave_and_refreshes_dynamic_slots():
    manager = WatchlistManager()

    sample_protocols = [
        {"slug": "aave-v3", "name": "Aave V3", "category": "Lending", "tvl": 200_000_000, "chains": ["Mantle"]},
        {"slug": "merchant-moe-dex", "name": "Merchant Moe", "category": "Dexes", "tvl": 50_000_000, "chains": ["Mantle"]},
        {"slug": "ondo-finance", "name": "Ondo Finance", "category": "RWA", "tvl": 30_000_000, "chains": ["Mantle"]},
        {"slug": "random-bridge", "name": "Random Bridge", "category": "Bridge", "tvl": 100_000_000, "chains": ["Mantle"]},
    ]

    ranked = manager.score_and_rank(sample_protocols)
    watchlist = manager.build_watchlist(ranked)

    slugs = [w["slug"] for w in watchlist]
    assert "aave-v3" in slugs

    aave_entry = next(w for w in watchlist if w["slug"] == "aave-v3")
    assert aave_entry["pinned"] is True

    non_pinned = [w for w in watchlist if not w["pinned"]]
    assert len(non_pinned) > 0
    assert all(w["pinned"] is False for w in non_pinned)


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


def test_dynamic_slots_limited():
    manager = WatchlistManager()

    protocols = [
        {"slug": f"proto-{i}", "name": f"Proto {i}", "category": "Dexes", "tvl": 1_000_000 * (20 - i)}
        for i in range(20)
    ]

    ranked = manager.score_and_rank(protocols)
    watchlist = manager.build_watchlist(ranked)

    non_pinned = [w for w in watchlist if not w["pinned"]]
    assert len(non_pinned) <= 15
