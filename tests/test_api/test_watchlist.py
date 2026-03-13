import pytest


def test_get_watchlist_returns_pinned_aave(client, seeded_watchlist):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert len(data["protocols"]) >= 1

    aave = next(p for p in data["protocols"] if p["slug"] == "aave-v3")
    assert aave["is_pinned"] is True
    assert aave["monitoring_tier"] == "special"


def test_get_watchlist_empty(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    assert response.json()["protocols"] == []


def test_refresh_watchlist(client):
    response = client.post("/api/watchlist/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refreshed"
    assert data["count"] > 0

    response = client.get("/api/watchlist")
    protocols = response.json()["protocols"]
    slugs = [p["slug"] for p in protocols]
    assert "aave-v3" in slugs
