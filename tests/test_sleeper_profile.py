"""Tests for Sleeper profile linking in ffpy-sleeper."""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.sleeper_web.app import create_sleeper_app


@pytest.fixture
def sleeper_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "sleeper.db"))
    yield db
    db.close()


@pytest.fixture
def auth_secret() -> str:
    return "super-secret-test-key-with-32-bytes"


@pytest.fixture
def client(sleeper_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch, auth_secret: str) -> TestClient:
    monkeypatch.setattr(Config, "SUPABASE_URL", "")
    monkeypatch.setattr(Config, "SUPABASE_BROWSER_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_JWT_SECRET", auth_secret)
    monkeypatch.setattr(Config, "WEB_AUTH_ENABLED", True)
    app = create_sleeper_app(db_path=str(sleeper_db.db_path), require_auth=True)
    with TestClient(app) as test_client:
        yield test_client


def _token(user_id: str, secret: str) -> str:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    payload = {
        "sub": user_id,
        "role": "authenticated",
        "aud": "authenticated",
        "email": f"{user_id}@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + __import__("datetime").timedelta(minutes=30),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_profile_requires_auth(client: TestClient):
    res = client.get("/api/profile/sleeper")
    assert res.status_code == 401


def test_link_and_get_profile(client: TestClient, auth_secret: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "ffpy.sleeper_web.profile.SleeperIntegration.get_user",
        lambda username: {"user_id": "uid_macker", "display_name": username},
    )
    headers = {"Authorization": f"Bearer {_token('user_a', auth_secret)}"}
    res = client.put("/api/profile/sleeper", json={"username": "macker1477"}, headers=headers)
    assert res.status_code == 200
    profile = res.json()["profile"]
    assert profile["sleeper_username"] == "macker1477"
    assert profile["sleeper_user_id"] == "uid_macker"

    res2 = client.get("/api/profile/sleeper", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["profile"]["sleeper_username"] == "macker1477"


def test_duplicate_sleeper_user_rejected(
    client: TestClient, auth_secret: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "ffpy.sleeper_web.profile.SleeperIntegration.get_user",
        lambda username: {"user_id": "uid_shared", "display_name": username},
    )
    headers_a = {"Authorization": f"Bearer {_token('user_a', auth_secret)}"}
    headers_b = {"Authorization": f"Bearer {_token('user_b', auth_secret)}"}
    assert (
        client.put("/api/profile/sleeper", json={"username": "macker1477"}, headers=headers_a).status_code
        == 200
    )
    res = client.put("/api/profile/sleeper", json={"username": "macker1477"}, headers=headers_b)
    assert res.status_code == 400
    assert "already linked" in res.json()["detail"]


def test_invalid_username_rejected(client: TestClient, auth_secret: str, monkeypatch: pytest.MonkeyPatch):
    def _missing(_username: str):
        raise RuntimeError("not found")

    monkeypatch.setattr("ffpy.sleeper_web.profile.SleeperIntegration.get_user", _missing)
    headers = {"Authorization": f"Bearer {_token('user_x', auth_secret)}"}
    res = client.put("/api/profile/sleeper", json={"username": "no_such_user"}, headers=headers)
    assert res.status_code == 400


def test_profile_isolation_between_users(
    client: TestClient, auth_secret: str, sleeper_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "ffpy.sleeper_web.profile.SleeperIntegration.get_user",
        lambda username: {"user_id": f"uid_{username}", "display_name": username},
    )
    headers_a = {"Authorization": f"Bearer {_token('user_a', auth_secret)}"}
    headers_b = {"Authorization": f"Bearer {_token('user_b', auth_secret)}"}
    client.put("/api/profile/sleeper", json={"username": "alice"}, headers=headers_a)
    client.put("/api/profile/sleeper", json={"username": "bob"}, headers=headers_b)

    profile_a = client.get("/api/profile/sleeper", headers=headers_a).json()["profile"]
    profile_b = client.get("/api/profile/sleeper", headers=headers_b).json()["profile"]
    assert profile_a["sleeper_username"] == "alice"
    assert profile_b["sleeper_username"] == "bob"

    sleeper_db.upsert_franchise("franchise:user_a:root1", "user_a", display_name="Alice League")
    sleeper_db.upsert_franchise("franchise:user_b:root2", "user_b", display_name="Bob League")

    franchises_a = client.get("/api/franchises", headers=headers_a).json()
    franchises_b = client.get("/api/franchises", headers=headers_b).json()
    assert len(franchises_a) == 1
    assert franchises_a[0]["display_name"] == "Alice League"
    assert len(franchises_b) == 1
    assert franchises_b[0]["display_name"] == "Bob League"
