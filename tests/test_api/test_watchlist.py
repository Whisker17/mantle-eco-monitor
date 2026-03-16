import pytest


def test_get_watchlist_returns_pinned_aave(client, seeded_watchlist):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert len(data["protocols"]) >= 1

    aave = next(p for p in data["protocols"] if p["slug"] == "aave-v3")
    assert aave["is_pinned"] is True
    assert aave["monitoring_tier"] == "special"
    assert aave["metrics"] == ["tvl", "supply", "borrowed", "utilization"]


def test_get_watchlist_empty(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    assert response.json()["protocols"] == []


def test_refresh_watchlist(client):
    response = client.post("/api/watchlist/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refreshed"
    assert data["count"] == 14

    response = client.get("/api/watchlist")
    protocols = response.json()["protocols"]
    slugs = [p["slug"] for p in protocols]
    assert "aave-v3" in slugs
    assert "merchant-moe" in slugs
    assert "stargate-finance" in slugs


def test_refresh_watchlist_uses_fixed_seed_even_when_fetch_is_monkeypatched(client, monkeypatch):
    from src.protocols.watchlist import WatchlistManager

    async def fake_fetch(self):
        return [
            {"slug": "merchant-moe-dex", "name": "Merchant Moe", "category": "Dexes", "tvl": 50_000_000, "chains": ["Mantle"]},
            {"slug": "ondo-yield-assets", "name": "Ondo Yield Assets", "category": "RWA", "tvl": 30_000_000, "chains": ["Mantle"]},
        ]

    monkeypatch.setattr(WatchlistManager, "fetch_mantle_protocols", fake_fetch)

    response = client.post("/api/watchlist/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 14

    response = client.get("/api/watchlist")
    slugs = [p["slug"] for p in response.json()["protocols"]]
    assert "merchant-moe" in slugs
    assert "ondo-yield-assets" in slugs
    assert "merchant-moe-dex" not in slugs
