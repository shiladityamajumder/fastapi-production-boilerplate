"""Payload encryption helpers for PostgreSQL-backed notification jobs."""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import AppSettings


def encrypt_payload(settings: AppSettings, payload: dict[str, Any]) -> bytes:
    """Encrypt a JSON notification payload before it enters PostgreSQL."""
    key = settings.background_payload_encryption_key_value
    if key is None:
        raise RuntimeError("Background payload encryption is not configured")
    return Fernet(key.encode()).encrypt(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    )


def decrypt_payload(settings: AppSettings, ciphertext: bytes) -> dict[str, Any]:
    """Decrypt a notification payload without logging any payload content."""
    key = settings.background_payload_encryption_key_value
    if key is None:
        raise RuntimeError("Background payload encryption is not configured")
    try:
        payload = json.loads(Fernet(key.encode()).decrypt(ciphertext))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ValueError("Notification payload cannot be decrypted") from exc
    if not isinstance(payload, dict):
        raise ValueError("Notification payload has an invalid shape")
    return payload


__all__ = ["decrypt_payload", "encrypt_payload"]
