from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ToolCallResult:
    tool_name: str
    arguments: dict[str, Any]
    raw_tool_call: dict[str, Any]


class LLMClient:
    _max_server_error_attempts = 3

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

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        return await self._complete(messages, response_format=response_format)

    async def _complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        created_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            for attempt in range(1, self._max_server_error_attempts + 1):
                body: dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                }
                if response_format is not None:
                    body["response_format"] = response_format

                response = await client.post(
                    f"{self._api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "HTTP-Referer": self._app_url,
                        "X-Title": self._app_name,
                    },
                    json=body,
                )
                if response.status_code >= 500 and attempt < self._max_server_error_attempts:
                    continue

                response.raise_for_status()
                payload = response.json()
                return payload["choices"][0]["message"]["content"]
        finally:
            if created_client:
                await client.aclose()

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ToolCallResult | None:
        created_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        allowed_tool_names = {
            tool["function"]["name"]
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
        }
        try:
            for attempt in range(1, self._max_server_error_attempts + 1):
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
                        "tools": tools,
                        "tool_choice": tool_choice,
                    },
                )
                if response.status_code >= 500 and attempt < self._max_server_error_attempts:
                    continue
                if response.status_code >= 400:
                    return None

                payload = response.json()
                message = payload["choices"][0]["message"]
                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    return None
                tool_call = tool_calls[0]
                function_payload = tool_call.get("function") or {}
                tool_name = function_payload.get("name")
                if not isinstance(tool_name, str) or tool_name not in allowed_tool_names:
                    return None
                arguments_raw = function_payload.get("arguments")
                if not isinstance(arguments_raw, str):
                    return None
                try:
                    arguments = json.loads(arguments_raw)
                except json.JSONDecodeError:
                    return None
                if not isinstance(arguments, dict):
                    return None
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=arguments,
                    raw_tool_call=tool_call,
                )
        finally:
            if created_client:
                await client.aclose()
