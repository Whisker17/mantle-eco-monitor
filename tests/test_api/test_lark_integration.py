from __future__ import annotations

import json

from src.main import create_app


class FakeBotQueryService:
    def __init__(self):
        self.messages: list[str] = []

    async def handle_message(self, text: str):
        self.messages.append(text)
        return {
            "intent": "metric_latest",
            "answer": "Mantle TVL is $1.5K.",
            "data": {},
            "source_urls": ["https://defillama.com/chain/Mantle"],
            "card": {"header": {"title": {"content": "Query Result", "tag": "plain_text"}}, "elements": []},
        }


class FakeLarkClient:
    def __init__(self):
        self.replies: list[dict] = []

    async def reply_card(self, *, message_id: str, card: dict):
        self.replies.append({"message_id": message_id, "card": card})
        return {"data": {"message_id": "om_reply"}}


def _make_settings():
    class FakeSettings:
        database_url = "sqlite+aiosqlite:///ignored.db"
        lark_bot_enabled = True
        lark_verification_token = "verify_x"
        lark_environment = "dev"
        lark_app_id = ""
        lark_app_secret = ""
        llm_api_base = ""
        llm_api_key = ""
        llm_model = ""
        llm_timeout_seconds = 30

    return FakeSettings()


def test_lark_events_route_handles_url_verification(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)

    response = test_app.post(
        "/api/integrations/lark/events",
        json={
            "type": "url_verification",
            "token": "verify_x",
            "challenge": "challenge-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-token"}


def test_lark_events_route_rejects_invalid_verification_token(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)

    response = test_app.post(
        "/api/integrations/lark/events",
        json={
            "type": "url_verification",
            "token": "wrong",
            "challenge": "challenge-token",
        },
    )

    assert response.status_code == 401


def test_lark_events_route_dispatches_message_event_to_bot_query_service(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    bot_service = FakeBotQueryService()
    lark_client = FakeLarkClient()

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)
    monkeypatch.setattr(lark_router_module, "_build_bot_query_service", lambda settings: bot_service)
    monkeypatch.setattr(lark_router_module, "_build_lark_client", lambda settings: lark_client)

    response = test_app.post(
        "/api/integrations/lark/events",
        json={
            "schema": "2.0",
            "header": {
                "event_id": "evt_1",
                "event_type": "im.message.receive_v1",
                "token": "verify_x",
            },
            "event": {
                "message": {
                    "message_id": "om_1",
                    "message_type": "text",
                    "content": json.dumps({"text": "@bot mantle tvl latest"}),
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert bot_service.messages == ["@bot mantle tvl latest"]
    assert lark_client.replies[0]["message_id"] == "om_1"


def test_lark_events_route_ignores_duplicate_event_ids(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    bot_service = FakeBotQueryService()
    lark_client = FakeLarkClient()

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)
    monkeypatch.setattr(lark_router_module, "_build_bot_query_service", lambda settings: bot_service)
    monkeypatch.setattr(lark_router_module, "_build_lark_client", lambda settings: lark_client)

    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "evt_duplicate",
            "event_type": "im.message.receive_v1",
            "token": "verify_x",
        },
        "event": {
            "message": {
                "message_id": "om_duplicate",
                "message_type": "text",
                "content": json.dumps({"text": "@bot mantle tvl latest"}),
            }
        },
    }

    first = test_app.post("/api/integrations/lark/events", json=payload)
    second = test_app.post("/api/integrations/lark/events", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"status": "ignored", "reason": "duplicate"}
    assert bot_service.messages == ["@bot mantle tvl latest"]
    assert len(lark_client.replies) == 1
