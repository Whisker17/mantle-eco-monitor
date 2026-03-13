import pytest


def test_get_alerts_returns_empty_when_no_data(client):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["alerts"] == []


def test_get_alerts_returns_filterable_results(client, seeded_alerts):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3

    response = client.get("/api/alerts?severity=high")
    data = response.json()
    assert data["total"] == 1
    assert data["alerts"][0]["severity"] == "high"


def test_get_alerts_filters_by_is_ath(client, seeded_alerts):
    response = client.get("/api/alerts?is_ath=true")
    data = response.json()
    assert data["total"] == 1
    assert data["alerts"][0]["is_ath"] is True


def test_review_alert(client, seeded_alerts):
    alerts_resp = client.get("/api/alerts")
    alert_id = alerts_resp.json()["alerts"][0]["id"]

    response = client.patch(
        f"/api/alerts/{alert_id}/review",
        json={"reviewed": True, "review_note": "Shared in weekly report"},
    )
    assert response.status_code == 200

    alerts_resp = client.get("/api/alerts?reviewed=true")
    assert alerts_resp.json()["total"] == 1


def test_review_alert_not_found(client):
    response = client.patch(
        "/api/alerts/9999/review",
        json={"reviewed": True},
    )
    assert response.status_code == 404
