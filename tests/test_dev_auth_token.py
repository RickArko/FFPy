"""Tests for local auth-token generation."""

from __future__ import annotations

import pytest

from ffpy.auth import SupabaseTokenVerifier, TokenVerificationError
from ffpy.config import Config
from ffpy.dev_auth_token import build_dev_token

SECRET = "super-secret-test-key-with-32-bytes"


def test_build_dev_token_verifies_as_confirmed_user():
    token = build_dev_token(
        secret=SECRET,
        email="demo@example.com",
        email_confirmed=True,
        ttl_minutes=30,
    )

    user = SupabaseTokenVerifier(
        jwt_secret=SECRET,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.email == "demo@example.com"
    assert user.email_confirmed is True
    assert user.role == "authenticated"


def test_build_dev_token_can_generate_unconfirmed_user():
    token = build_dev_token(
        secret=SECRET,
        email="demo@example.com",
        email_confirmed=False,
        ttl_minutes=30,
    )

    user = SupabaseTokenVerifier(
        jwt_secret=SECRET,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.email_confirmed is False


def test_build_dev_token_includes_issuer_when_supabase_url_configured(monkeypatch: pytest.MonkeyPatch):
    """run-auth-local loads the repo .env (SUPABASE_URL set) — the verifier then
    requires iss={url}/auth/v1, so locally minted tokens must carry the same claim."""
    url = "https://demo-project.supabase.co"
    monkeypatch.setattr(Config, "SUPABASE_URL", url)

    token = build_dev_token(secret=SECRET, email="demo@example.com", ttl_minutes=30)

    user = SupabaseTokenVerifier(
        supabase_url=url,
        jwt_secret=SECRET,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.email == "demo@example.com"
    assert user.claims["iss"] == f"{url}/auth/v1"


def test_build_dev_token_issuer_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Config, "SUPABASE_URL", "https://configured.supabase.co")

    token = build_dev_token(
        secret=SECRET,
        email="demo@example.com",
        ttl_minutes=30,
        issuer="https://override.example/auth/v1",
    )

    user = SupabaseTokenVerifier(
        supabase_url="https://override.example",
        jwt_secret=SECRET,
        audience="authenticated",
        fetch_user_on_verify=False,
    ).verify_access_token(token)

    assert user.claims["iss"] == "https://override.example/auth/v1"


def test_verifier_rejects_token_missing_issuer_when_configured(monkeypatch: pytest.MonkeyPatch):
    """Regression guard: a token minted without iss must fail against a
    URL-configured verifier (this is the failure the issuer fix addresses)."""
    url = "https://demo-project.supabase.co"
    monkeypatch.setattr(Config, "SUPABASE_URL", "")  # mint without issuer

    token = build_dev_token(secret=SECRET, email="demo@example.com", ttl_minutes=30)
    monkeypatch.setattr(Config, "SUPABASE_URL", url)

    verifier = SupabaseTokenVerifier(
        supabase_url=url,
        jwt_secret=SECRET,
        audience="authenticated",
        fetch_user_on_verify=False,
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify_access_token(token)
