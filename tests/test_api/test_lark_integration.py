from __future__ import annotations

import base64
import json
from hashlib import sha256

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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
        bot_external_actions_enabled = False
        lark_verification_token = "verify_x"
        lark_encrypt_key = "encrypt-key-123"
        lark_environment = "dev"
        lark_app_id = ""
        lark_app_secret = ""
        lark_base_url = "https://open.larksuite.com"
        llm_api_base = ""
        llm_api_key = ""
        llm_model = ""
        llm_app_name = "mantle-eco-monitor"
        llm_app_url = "https://github.com/Whisker17/mantle-eco-monitor"
        llm_timeout_seconds = 30

    return FakeSettings()


def _encrypt_payload(payload: dict, encrypt_key: str) -> str:
    key = sha256(encrypt_key.encode("utf-8")).digest()
    iv = key[:16]
    plaintext = json.dumps(payload).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


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


def test_lark_events_route_handles_encrypted_url_verification(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)

    encrypted = _encrypt_payload(
        {
            "type": "url_verification",
            "token": "verify_x",
            "challenge": "challenge-token-encrypted",
        },
        "encrypt-key-123",
    )

    response = test_app.post(
        "/api/integrations/lark/events",
        json={"encrypt": encrypted},
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-token-encrypted"}


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
                    "chat_type": "group",
                    "mentions": [{"name": "bot"}],
                    "content": json.dumps({"text": "@bot mantle tvl latest"}),
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert bot_service.messages == ["@bot mantle tvl latest"]
    assert lark_client.replies[0]["message_id"] == "om_1"


def test_lark_events_route_dispatches_encrypted_message_event_to_bot_query_service(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    bot_service = FakeBotQueryService()
    lark_client = FakeLarkClient()

    monkeypatch.setattr(lark_router_module, "Settings", _make_settings)
    monkeypatch.setattr(lark_router_module, "_build_bot_query_service", lambda settings: bot_service)
    monkeypatch.setattr(lark_router_module, "_build_lark_client", lambda settings: lark_client)

    encrypted = _encrypt_payload(
        {
            "schema": "2.0",
            "header": {
                "event_id": "evt_enc_1",
                "event_type": "im.message.receive_v1",
                "token": "verify_x",
            },
            "event": {
                "message": {
                    "message_id": "om_enc_1",
                    "message_type": "text",
                    "chat_type": "group",
                    "mentions": [{"name": "bot"}],
                    "content": json.dumps({"text": "@bot mantle tvl latest"}),
                }
            },
        },
        "encrypt-key-123",
    )

    response = test_app.post(
        "/api/integrations/lark/events",
        json={"encrypt": encrypted},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert bot_service.messages == ["@bot mantle tvl latest"]
    assert lark_client.replies[0]["message_id"] == "om_enc_1"


def test_lark_events_route_rejects_message_events_when_bot_is_disabled(test_app, monkeypatch):
    from src.integrations.lark import router as lark_router_module

    class DisabledBotSettings:
        database_url = "sqlite+aiosqlite:///ignored.db"
        lark_bot_enabled = False
        bot_external_actions_enabled = False
        lark_verification_token = "verify_x"
        lark_encrypt_key = "encrypt-key-123"
        lark_environment = "dev"
        lark_app_id = ""
        lark_app_secret = ""
        lark_base_url = "https://open.larksuite.com"
        llm_api_base = ""
        llm_api_key = ""
        llm_model = ""
        llm_app_name = "mantle-eco-monitor"
        llm_app_url = "https://github.com/Whisker17/mantle-eco-monitor"
        llm_timeout_seconds = 30

    monkeypatch.setattr(lark_router_module, "Settings", lambda: DisabledBotSettings())

    response = test_app.post(
        "/api/integrations/lark/events",
        json={
            "schema": "2.0",
            "header": {
                "event_id": "evt_disabled",
                "event_type": "im.message.receive_v1",
                "token": "verify_x",
            },
            "event": {
                "message": {
                    "message_id": "om_disabled",
                    "message_type": "text",
                    "chat_type": "group",
                    "mentions": [{"name": "bot"}],
                    "content": json.dumps({"text": "@bot mantle tvl latest"}),
                }
            },
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Lark bot is disabled"}


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
                "chat_type": "group",
                "mentions": [{"name": "bot"}],
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


def test_lark_events_route_ignores_group_messages_that_do_not_mention_bot(test_app, monkeypatch):
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
                "event_id": "evt_no_mention",
                "event_type": "im.message.receive_v1",
                "token": "verify_x",
            },
            "event": {
                "message": {
                    "message_id": "om_no_mention",
                    "message_type": "text",
                    "chat_type": "group",
                    "mentions": [],
                    "content": json.dumps({"text": "mantle tvl latest"}),
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "not_addressed"}
    assert bot_service.messages == []
    assert lark_client.replies == []


def test_build_bot_query_service_passes_openrouter_metadata(monkeypatch):
    from src.integrations.lark import router as lark_router_module

    class FakeSettings:
        database_url = "sqlite+aiosqlite:///ignored.db"
        bot_external_actions_enabled = False
        llm_api_base = "https://openrouter.ai/api/v1"
        llm_api_key = "key_x"
        llm_model = "nvidia/nemotron-3-super-120b-a12b:free"
        llm_app_name = "mantle-eco-monitor"
        llm_app_url = "https://github.com/Whisker17/mantle-eco-monitor"
        llm_timeout_seconds = 45

    captured = {}

    class FakeLLMClient:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr(lark_router_module, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(lark_router_module, "get_session_factory", lambda settings: "session-factory")

    service = lark_router_module._build_bot_query_service(FakeSettings())

    assert service._session_factory == "session-factory"
    assert captured["kwargs"]["app_name"] == "mantle-eco-monitor"
    assert captured["kwargs"]["app_url"] == "https://github.com/Whisker17/mantle-eco-monitor"


def test_build_lark_client_uses_configured_base_url():
    from src.integrations.lark import router as lark_router_module

    class FakeSettings:
        lark_app_id = "cli_x"
        lark_app_secret = "secret_x"
        lark_base_url = "https://open.feishu.cn"

    client = lark_router_module._build_lark_client(FakeSettings())

    assert client._base_url == "https://open.feishu.cn"
