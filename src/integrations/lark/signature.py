from __future__ import annotations

import base64
import json
from hashlib import sha256

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def verify_callback_token(token: str | None, verification_token: str) -> bool:
    return bool(token) and token == verification_token


def decrypt_callback_payload(payload: dict, encrypt_key: str) -> dict:
    encrypted = payload.get("encrypt")
    if not isinstance(encrypted, str):
        return payload
    if not encrypt_key:
        raise ValueError("Missing Lark encrypt key")

    key = sha256(encrypt_key.encode("utf-8")).digest()
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(decrypted) + unpadder.finalize()
    return json.loads(plaintext.decode("utf-8"))
