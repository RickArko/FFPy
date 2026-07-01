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

    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_league",
        lambda league_id: {"name": "Test League", "season": 2024, "total_rosters": 10},
    )
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_league_users",
        lambda league_id: [
            {"user_id": "o1", "display_name": "owner1", "metadata": {"team_name": "Team A"}},
            {"user_id": "o2", "display_name": "owner2", "metadata": {"team_name": "Team B"}},
        ],
    )
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_rosters",
        lambda league_id: [
            {
                "roster_id": 1,
                "owner_id": "o1",
                "settings": {"wins": 5, "losses": 3, "ties": 0, "fpts": 100, "fpts_against": 80},
                "players": ["1234"],
            },
            {
                "roster_id": 2,
                "owner_id": "o2",
                "settings": {"wins": 3, "losses": 5, "ties": 0, "fpts": 80, "fpts_against": 100},
                "players": ["5678"],
            },
        ],
    )
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_matchups",
        lambda league_id, week: [{"roster_id": 1, "matchup_id": 2, "points": 100}],
    )
    monkeypatch.setattr(
        "ffpy.draft_strategy.load_sleeper_players",
        lambda force=False: {
            "1234": {"full_name": "Player One", "position": "RB", "team": "KC"},
            "5678": {"full_name": "Player Two", "position": "WR", "team": "MIA"},
        },
    )

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


def test_sleeper_credentials_skip_encryption(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import ffpy.league_api as league_api_module

    monkeypatch.setattr(league_api_module, "MASTER_KEY", None)
    res = client.post(
        "/api/leagues/credentials",
        json={"provider": "sleeper", "credentials": {"username": "macker1477"}, "label": ""},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_sleeper_discover(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class FakeSleeper:
        @staticmethod
        def get_user(username: str) -> dict:
            if username == "macker1477":
                return {"user_id": "uid123"}
            return {}

        @staticmethod
        def get_user_leagues(user_id: str, season: int) -> list[dict]:
            return [
                {
                    "league_id": "lg1",
                    "name": "Tight ends and loose lips",
                    "season": season,
                    "status": "pre_draft",
                    "total_rosters": 10,
                }
            ]

    monkeypatch.setattr("ffpy.league_api.SleeperIntegration", FakeSleeper)
    res = client.get("/api/leagues/sleeper/discover?username=macker1477&season=2026")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["league_id"] == "lg1"
    assert data[0]["name"] == "Tight ends and loose lips"


def test_import_sleeper_username_visible_when_auth_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_league",
        lambda league_id: {"name": "Test League", "season": 2024, "total_rosters": 10},
    )
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_league_users",
        lambda league_id: [{"user_id": "o1", "display_name": "owner1", "metadata": {"team_name": "Team A"}}],
    )
    monkeypatch.setattr(
        "ffpy.league_api.SleeperIntegration.get_rosters",
        lambda league_id: [
            {
                "roster_id": 1,
                "owner_id": "o1",
                "settings": {"wins": 5, "losses": 3, "ties": 0, "fpts": 100, "fpts_against": 80},
                "players": ["1234"],
            },
        ],
    )
    monkeypatch.setattr("ffpy.league_api.SleeperIntegration.get_matchups", lambda league_id, week: [])
    monkeypatch.setattr(
        "ffpy.draft_strategy.load_sleeper_players",
        lambda force=False: {"1234": {"full_name": "Player One", "position": "RB", "team": "KC"}},
    )

    res = client.post(
        "/api/leagues/import",
        json={
            "provider": "sleeper",
            "league_id": "test_league_2",
            "season": 2024,
            "sleeper_username": "macker1477",
        },
    )
    assert res.status_code == 200

    res2 = client.get("/api/leagues")
    assert res2.status_code == 200
    leagues = res2.json()
    assert len(leagues) == 1
    assert leagues[0]["user_id"] == "macker1477"


def test_draft_help_endpoint(client: TestClient, api_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch):
    import pandas as pd

    # Seed ADP for draft board
    adp = pd.DataFrame(
        {
            "player_name": ["Alpha RB", "Beta WR", "Gamma TE"],
            "position": ["RB", "WR", "TE"],
            "platform": ["fantasypros"] * 3,
            "adp": [10.0, 15.0, 40.0],
            "adp_high": [8.0, 12.0, 35.0],
            "adp_low": [12.0, 18.0, 45.0],
        }
    )
    api_db.store_adp(adp, season=2026)

    league_data = {
        "league": {
            "league_id": "sleeper:draft_test",
            "provider": "sleeper",
            "name": "Draft Test",
            "season": 2026,
            "num_teams": 10,
        },
        "teams": [
            {
                "team_id": "sleeper:draft_test:t1",
                "name": "My Team",
                "owner": "user_draft",
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0,
                "points_against": 0,
                "rank": 1,
                "roster": [{"player": "Josh Allen", "position": "QB", "team": "BUF"}],
            },
            {
                "team_id": "sleeper:draft_test:t2",
                "name": "Other",
                "owner": "other",
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0,
                "points_against": 0,
                "rank": 2,
                "roster": [],
            },
        ],
        "matchups": [],
    }
    api_db.store_user_league("anon", league_data)

    res = client.post(
        "/api/leagues/sleeper:draft_test/draft-help",
        json={"team_id": "sleeper:draft_test:t1", "num_players": 3, "pick_slots": [1, 20, 21]},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["season"] == 2026
    assert len(payload["rankings"]) == 3
    assert all("reasons" in r and r["reasons"] for r in payload["rankings"])
    assert len(payload["picks"]) == 3
    assert payload["picks"][0]["pick_slot"] == 1
