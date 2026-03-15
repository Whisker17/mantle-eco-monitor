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
    assert captured["body"] == {
        "model": "gpt-x",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Say hi"},
        ],
    }
