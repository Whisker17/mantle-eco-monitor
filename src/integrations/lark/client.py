from __future__ import annotations

import json
import time
from typing import Any

import httpx


class LarkClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._tenant_access_token: str | None = None
        self._tenant_access_token_expires_at = 0.0

    async def send_card(self, *, chat_id: str, card: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_tenant_access_token()
        created_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                f"{self._base_url}/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card),
                },
            )
            response.raise_for_status()
            return response.json()
        finally:
            if created_client:
                await client.aclose()

    async def _get_tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._tenant_access_token_expires_at:
            return self._tenant_access_token

        created_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()
            self._tenant_access_token = payload["tenant_access_token"]
            self._tenant_access_token_expires_at = now + int(payload.get("expire", 0)) - 60
            return self._tenant_access_token
        finally:
            if created_client:
                await client.aclose()
