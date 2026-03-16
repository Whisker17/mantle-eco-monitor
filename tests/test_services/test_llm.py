from __future__ import annotations

import json

import httpx
import pytest

from src.services.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_client_posts_openai_compatible_chat_completion_request():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["referer"] = request.headers.get("HTTP-Referer")
        captured["title"] = request.headers.get("X-Title")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "hello from llm",
                        }
                    }
                ]
            },
        )

    client = LLMClient(
        api_base="https://llm.example.com/v1",
        api_key="secret-key",
        model="gpt-x",
        app_name="mantle-eco-monitor",
        app_url="https://github.com/Whisker17/mantle-eco-monitor",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await client.complete(
        [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Say hi"},
        ]
    )

    assert result == "hello from llm"
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer secret-key"
    assert captured["referer"] == "https://github.com/Whisker17/mantle-eco-monitor"
    assert captured["title"] == "mantle-eco-monitor"
    assert captured["body"] == {
        "model": "gpt-x",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Say hi"},
        ],
    }


@pytest.mark.asyncio
async def test_llm_client_retries_on_server_error_and_returns_first_success():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "recovered",
                        }
                    }
                ]
            },
        )

    client = LLMClient(
        api_base="https://llm.example.com/v1",
        api_key="secret-key",
        model="gpt-x",
        app_name="mantle-eco-monitor",
        app_url="https://github.com/Whisker17/mantle-eco-monitor",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await client.complete([{"role": "user", "content": "retry please"}])

    assert result == "recovered"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_llm_client_includes_response_format_when_requested():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"intent":"metric_latest","entity":"mantle","metric_name":"tvl"}',
                        }
                    }
                ]
            },
        )

    client = LLMClient(
        api_base="https://llm.example.com/v1",
        api_key="secret-key",
        model="gpt-x",
        app_name="mantle-eco-monitor",
        app_url="https://github.com/Whisker17/mantle-eco-monitor",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await client.complete(
        [{"role": "user", "content": "route this"}],
        response_format={"type": "json_object"},
    )

    assert result == '{"intent":"metric_latest","entity":"mantle","metric_name":"tvl"}'
    assert captured["body"] == {
        "model": "gpt-x",
        "messages": [
            {"role": "user", "content": "route this"},
        ],
        "response_format": {"type": "json_object"},
    }
