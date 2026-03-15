from __future__ import annotations


def verify_callback_token(token: str | None, verification_token: str) -> bool:
    return bool(token) and token == verification_token
