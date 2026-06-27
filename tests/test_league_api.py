"""HTTP-level tests for the league API."""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.league_api import create_league_app


@pytest.fixture
def api_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "league-api.db"))
    yield db
    db.close()


@pytest.fixture
def client(api_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(Config, "SUPABASE_URL", "")
    monkeypatch.setattr(Config, "SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_ANON_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_BROWSER_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_JWT_SECRET", "super-secret-test-key-with-32-bytes")
    import ffpy.league_api as league_api_module
    monkeypatch.setattr(league_api_module, "MASTER_KEY", b"super-secret-test-key-with-32-bytes")
    app = create_league_app(db_path=str(api_db.db_path), require_auth=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_secret() -> str:
    return "super-secret-test-key-with-32-bytes"


def _generate_test_token(user_id: str, secret: str) -> str:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    payload = {
        "sub": user_id,
        "role": "authenticated",
        "email": "test@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + __import__("datetime").timedelta(minutes=30),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_auth_me_unauthenticated(client: TestClient):
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is False


def test_store_and_list_credentials(client: TestClient, auth_secret: str):
    token = _generate_test_token("user_abc", auth_secret)
    res = client.post(
        "/api/leagues/credentials",
        json={"provider": "espn", "credentials": {"swid": "test", "s2": "test"}, "label": "My League"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    res2 = client.get(
        "/api/leagues/credentials",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    data = res2.json()
    assert any(c["provider"] == "espn" for c in data)


def test_delete_credentials(client: TestClient, auth_secret: str):
    token = _generate_test_token("user_del", auth_secret)
    client.post(
        "/api/leagues/credentials",
        json={"provider": "espn", "credentials": {"swid": "x", "s2": "y"}, "label": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    res = client.delete(
        "/api/leagues/credentials/espn",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    res2 = client.get(
        "/api/leagues/credentials",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    assert res2.json() == []


def test_import_requires_credentials(client: TestClient, auth_secret: str):
    token = _generate_test_token("user_imp", auth_secret)
    res = client.post(
        "/api/leagues/import",
        json={"provider": "espn", "league_id": "123", "season": 2024},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "No stored credentials" in res.json()["detail"]


def test_list_leagues_empty(client: TestClient, auth_secret: str):
    token = _generate_test_token("user_empty", auth_secret)
    res = client.get("/api/leagues", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


def test_import_round_trip_sleeper(client: TestClient, auth_secret: str, monkeypatch: pytest.MonkeyPatch):
    token = _generate_test_token("user_slp", auth_secret)

    # Patch SleeperIntegration to avoid network calls
    class FakeSleeper:
        @staticmethod
        def get_league(league_id: str) -> dict:
            return {"name": "Test League", "season": 2024, "total_rosters": 10}

        @staticmethod
        def get_rosters(league_id: str) -> list[dict]:
            return [
                {
                    "owner_id": "o1",
                    "settings": {"wins": 5, "losses": 3, "ties": 0, "fpts": 100, "fpts_against": 80, "team_name": "Team A"},
                    "players": ["1234"],
                },
                {
                    "owner_id": "o2",
                    "settings": {"wins": 3, "losses": 5, "ties": 0, "fpts": 80, "fpts_against": 100, "team_name": "Team B"},
                    "players": ["5678"],
                },
            ]

        @staticmethod
        def get_matchups(league_id: str, week: int) -> list[dict]:
            return [{"roster_id": 1, "matchup_id": 2, "points": 100}]

    monkeypatch.setattr("ffpy.league_api.SleeperIntegration", FakeSleeper)

    res = client.post(
        "/api/leagues/import",
        json={"provider": "sleeper", "league_id": "test_league_1", "season": 2024},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "imported"
    assert data["teams"] == 2

    # List leagues
    res2 = client.get("/api/leagues", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    leagues = res2.json()
    assert len(leagues) == 1
    assert leagues[0]["provider"] == "sleeper"

    # Get teams
    league_id = data["league_id"]
    res3 = client.get(f"/api/leagues/{league_id}/teams", headers={"Authorization": f"Bearer {token}"})
    assert res3.status_code == 200
    teams = res3.json()
    assert len(teams) == 2

    # Get matchups
    res4 = client.get(f"/api/leagues/{league_id}/matchups/1", headers={"Authorization": f"Bearer {token}"})
    assert res4.status_code == 200

    # Delete league
    res5 = client.delete(f"/api/leagues/{league_id}", headers={"Authorization": f"Bearer {token}"})
    assert res5.status_code == 200

    res6 = client.get("/api/leagues", headers={"Authorization": f"Bearer {token}"})
    assert res6.json() == []
