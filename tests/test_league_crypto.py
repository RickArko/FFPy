"""Encryption round-trip tests for league credential encryption."""

from __future__ import annotations

import pytest

from ffpy.league_crypto import decrypt_credentials, encrypt_credentials


class TestCredentialEncryption:
    """Encryption round-trip tests."""

    def test_encrypt_decrypt(self):
        creds = {"swid": "ABC-123", "s2": "long-cookie-value"}
        master = b"my-secret-key-32-bytes-long!!!!!"
        cipher = encrypt_credentials(creds, "user_1", master)
        assert cipher != str(creds)
        decrypted = decrypt_credentials(cipher, "user_1", master)
        assert decrypted == creds

    def test_wrong_user_cannot_decrypt(self):
        creds = {"swid": "ABC-123", "s2": "long-cookie-value"}
        master = b"my-secret-key-32-bytes-long!!!!!"
        cipher = encrypt_credentials(creds, "user_1", master)
        with pytest.raises(Exception):
            decrypt_credentials(cipher, "user_2", master)

    def test_different_master_key(self):
        creds = {"token": "abc"}
        master1 = b"my-secret-key-32-bytes-long!!!!!"
        master2 = b"another-key-32-bytes-long!!!!!"
        cipher = encrypt_credentials(creds, "u1", master1)
        with pytest.raises(Exception):
            decrypt_credentials(cipher, "u1", master2)
