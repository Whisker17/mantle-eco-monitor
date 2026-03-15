from __future__ import annotations

from typing import Any

import httpx


class LLMClient:
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        app_name: str,
        app_url: str,
        timeout_seconds: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._app_name = app_name
        self._app_url = app_url
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def complete(self, messages: list[dict[str, Any]]) -> str:
        created_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": self._app_url,
                    "X-Title": self._app_name,
                },
                json={
                    "model": self._model,
                    "messages": messages,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        finally:
            if created_client:
                await client.aclose()
