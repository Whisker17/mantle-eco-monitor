from __future__ import annotations

import json

import httpx
import pytest

from src.integrations.lark.client import LarkClient


@pytest.mark.asyncio
async def test_lark_client_fetches_tenant_token_and_sends_interactive_card():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            captured["auth_body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )

        captured["message_url"] = str(request.url)
        captured["message_auth"] = request.headers.get("Authorization")
        captured["message_body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"code": 0, "data": {"message_id": "om_123"}},
        )

    client = LarkClient(
        app_id="cli_x",
        app_secret="secret_x",
        base_url="https://open.feishu.cn",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await client.send_card(
        chat_id="oc_test_chat",
        card={"header": {"title": {"content": "Alert", "tag": "plain_text"}}},
    )

    assert result["data"]["message_id"] == "om_123"
    assert captured["auth_body"] == {
        "app_id": "cli_x",
        "app_secret": "secret_x",
    }
    assert captured["message_url"] == "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    assert captured["message_auth"] == "Bearer tenant-token"
    assert captured["message_body"] == {
        "receive_id": "oc_test_chat",
        "msg_type": "interactive",
        "content": json.dumps({"header": {"title": {"content": "Alert", "tag": "plain_text"}}}),
    }


@pytest.mark.asyncio
async def test_lark_client_reuses_cached_tenant_token():
    calls = {"auth": 0, "message": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            calls["auth"] += 1
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200},
            )

        calls["message"] += 1
        return httpx.Response(
            200,
            json={"code": 0, "data": {"message_id": f"om_{calls['message']}"}},
        )

    client = LarkClient(
        app_id="cli_x",
        app_secret="secret_x",
        base_url="https://open.feishu.cn",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await client.send_card(chat_id="chat_a", card={"header": {"title": {"content": "A", "tag": "plain_text"}}})
    await client.send_card(chat_id="chat_b", card={"header": {"title": {"content": "B", "tag": "plain_text"}}})

    assert calls == {"auth": 1, "message": 2}
