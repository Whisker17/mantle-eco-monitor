import pytest


def test_get_metrics_latest_empty(client):
    response = client.get("/api/metrics/latest")
    assert response.status_code == 200
    assert response.json()["snapshots"] == []


def test_get_metrics_latest_returns_data(client, seeded_snapshots):
    response = client.get("/api/metrics/latest")
    data = response.json()
    assert len(data["snapshots"]) >= 1
    assert data["snapshots"][0]["entity"] == "mantle"


def test_get_metrics_history_returns_ordered_points(client, seeded_snapshots):
    response = client.get("/api/metrics/history?entity=mantle&metric_name=tvl")
    assert response.status_code == 200
    data = response.json()
    assert len(data["snapshots"]) == 5
    dates = [s["collected_at"] for s in data["snapshots"]]
    assert dates == sorted(dates, reverse=True)


def test_get_metrics_history_requires_entity(client):
    response = client.get("/api/metrics/history?metric_name=tvl")
    assert response.status_code == 422
