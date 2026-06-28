"""Credential encryption using Fernet (AES-128-CBC + HMAC)."""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet


def _derive_key(user_id: str, master_key: bytes) -> bytes:
    """Derive a per-user Fernet key from the master key + user ID."""
    raw = hashlib.sha256(master_key + user_id.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_credentials(creds: dict, user_id: str, master_key: bytes) -> str:
    """Encrypt a credentials dict to a Fernet ciphertext string."""
    key = _derive_key(user_id, master_key)
    f = Fernet(key)
    return f.encrypt(json.dumps(creds).encode()).decode()


def decrypt_credentials(ciphertext: str, user_id: str, master_key: bytes) -> dict:
    """Decrypt a Fernet ciphertext string back to a credentials dict."""
    key = _derive_key(user_id, master_key)
    f = Fernet(key)
    return json.loads(f.decrypt(ciphertext.encode()))
