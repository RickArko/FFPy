"""Tests for local auth-token generation."""

from __future__ import annotations

from ffpy.auth import SupabaseTokenVerifier
from ffpy.dev_auth_token import build_dev_token


def test_build_dev_token_verifies_as_confirmed_user():
    secret = "super-secret-test-key-with-32-bytes"
    token = build_dev_token(
        secret=secret,
        email="demo@example.com",
        email_confirmed=True,
        ttl_minutes=30,
    )

    user = SupabaseTokenVerifier(
        jwt_secret=secret,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.email == "demo@example.com"
    assert user.email_confirmed is True
    assert user.role == "authenticated"


def test_build_dev_token_can_generate_unconfirmed_user():
    secret = "super-secret-test-key-with-32-bytes"
    token = build_dev_token(
        secret=secret,
        email="demo@example.com",
        email_confirmed=False,
        ttl_minutes=30,
    )

    user = SupabaseTokenVerifier(
        jwt_secret=secret,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.email_confirmed is False
