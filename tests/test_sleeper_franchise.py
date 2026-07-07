"""Franchise chain discovery and sync tests."""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.sleeper_web.app import create_sleeper_app
from ffpy.sleeper_web.franchise import FranchiseService


@pytest.fixture
def sleeper_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "franchise.db"))
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


def test_walk_chain_groups_previous_league_id(monkeypatch: pytest.MonkeyPatch):
    payloads = {
        "2026": {"league_id": "2026", "season": 2026, "name": "Dynasty", "previous_league_id": "2025"},
        "2025": {"league_id": "2025", "season": 2025, "name": "Dynasty", "previous_league_id": None},
    }

    def fake_get_league(league_id: str):
        return payloads[league_id]

    monkeypatch.setattr("ffpy.sleeper_web.franchise.SleeperIntegration.get_league", fake_get_league)
    chain = FranchiseService._walk_chain("2026")
    assert len(chain) == 2
    assert chain[0]["league_id"] == "2026"
    assert chain[-1]["league_id"] == "2025"


def test_sync_franchises_imports_multiple_seasons(
    sleeper_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch, auth_secret: str, client: TestClient
):
    sleeper_db.upsert_sleeper_profile(
        "user_sync", sleeper_user_id="uid_macker", sleeper_username="macker1477"
    )

    def fake_user_leagues(user_id: str, season: int):
        if season == 2026:
            return [{"league_id": "1312118348556828672", "name": "Tight ends and loose lips", "season": 2026}]
        return []

    league_payloads = {
        "1312118348556828672": {
            "league_id": "1312118348556828672",
            "season": 2026,
            "name": "Tight ends and loose lips",
            "previous_league_id": "prev_league",
            "total_rosters": 10,
            "status": "pre_draft",
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"],
            "scoring_settings": {"rec": 1.0},
        },
        "prev_league": {
            "league_id": "prev_league",
            "season": 2025,
            "name": "Tight ends and loose lips",
            "previous_league_id": None,
            "total_rosters": 10,
            "status": "complete",
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"],
            "scoring_settings": {"rec": 1.0},
        },
    }

    monkeypatch.setattr(
        "ffpy.sleeper_web.franchise.SleeperIntegration.get_user_leagues",
        fake_user_leagues,
    )
    monkeypatch.setattr(
        "ffpy.sleeper_web.franchise.SleeperIntegration.get_league",
        lambda league_id: league_payloads[str(league_id)],
    )
    monkeypatch.setattr(
        "ffpy.sleeper_import.SleeperIntegration.get_rosters",
        lambda league_id: [
            {
                "roster_id": 1,
                "owner_id": "uid_macker",
                "players": ["p1"],
                "settings": {
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "fpts": 0,
                    "fpts_against": 0,
                    "draft_slot": 1,
                },
            }
        ],
    )
    monkeypatch.setattr(
        "ffpy.sleeper_import.SleeperIntegration.get_league_users",
        lambda league_id: [{"user_id": "uid_macker", "display_name": "macker1477", "metadata": {}}],
    )
    monkeypatch.setattr("ffpy.sleeper_import.SleeperIntegration.get_matchups", lambda league_id, week: [])
    monkeypatch.setattr(
        "ffpy.draft_strategy.load_sleeper_players",
        lambda force=False: {"p1": {"full_name": "Player One", "position": "RB", "team": "KC"}},
    )

    headers = {"Authorization": f"Bearer {_token('user_sync', auth_secret)}"}
    res = client.post("/api/franchises/sync", headers=headers)
    assert res.status_code == 200
    franchises = res.json()["franchises"]
    assert len(franchises) == 1
    assert len(franchises[0]["seasons"]) >= 2

    res2 = client.post("/api/franchises/sync", headers=headers)
    assert res2.status_code == 200
    assert len(res2.json()["franchises"]) == 1


def test_sync_reclaims_leagues_imported_under_sleeper_username(
    sleeper_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch, auth_secret: str, client: TestClient
):
    """Franchise sync must own leagues previously stored under a Sleeper username key."""
    from ffpy.sleeper_import import import_from_sleeper

    supabase_user = "045c28a4-9566-4d3c-a4c1-6166cf55dce3"
    sleeper_db.upsert_sleeper_profile(
        supabase_user, sleeper_user_id="1263503584687833088", sleeper_username="macker1477"
    )

    monkeypatch.setattr(
        "ffpy.sleeper_web.import_service.import_from_sleeper",
        lambda league_id, season: {
            "league": {
                "league_id": f"sleeper:{league_id}",
                "provider": "sleeper",
                "name": "Tight ends and loose lips",
                "season": season,
                "sleeper_league_id": str(league_id),
                "status": "pre_draft",
            },
            "teams": [
                {
                    "team_id": f"sleeper:{league_id}:1",
                    "name": "Team One",
                    "owner": "macker1477",
                }
            ],
            "matchups": [],
        },
    )

    legacy = import_from_sleeper("1312118348556828672", 2026)
    sleeper_db.store_user_league("macker1477", legacy)
    assert sleeper_db.get_user_league("sleeper:1312118348556828672", supabase_user) is None

    def fake_user_leagues(user_id: str, season: int):
        if season == 2026:
            return [{"league_id": "1312118348556828672", "name": "Tight ends and loose lips", "season": 2026}]
        return []

    league_payloads = {
        "1312118348556828672": {
            "league_id": "1312118348556828672",
            "season": 2026,
            "name": "Tight ends and loose lips",
            "previous_league_id": None,
        },
    }

    monkeypatch.setattr(
        "ffpy.sleeper_web.franchise.SleeperIntegration.get_user_leagues",
        fake_user_leagues,
    )
    monkeypatch.setattr(
        "ffpy.sleeper_web.franchise.SleeperIntegration.get_league",
        lambda league_id: league_payloads[str(league_id)],
    )

    headers = {"Authorization": f"Bearer {_token(supabase_user, auth_secret)}"}
    sync = client.post("/api/franchises/sync", headers=headers)
    assert sync.status_code == 200

    teams = client.get("/api/leagues/sleeper%3A1312118348556828672/teams", headers=headers)
    assert teams.status_code == 200
    assert teams.json()
    assert sleeper_db.get_user_league("sleeper:1312118348556828672", supabase_user) is not None


@pytest.mark.skip(reason="Optional live Sleeper API check")
def test_franchise_chain_real_sleeper_user(monkeypatch: pytest.MonkeyPatch):
    """Optional live API check using the official Sleeper account."""
    from ffpy.integrations.sleeper import SleeperIntegration

    user = SleeperIntegration.get_user("sleeper")
    user_id = user.get("user_id")
    assert user_id
    leagues = SleeperIntegration.get_user_leagues(str(user_id), 2024)
    assert isinstance(leagues, list)
