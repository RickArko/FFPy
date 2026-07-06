"""Golden-path draft help tests for macker1477 league."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.sleeper_import import compute_snake_pick_slots
from ffpy.sleeper_web.app import create_sleeper_app

MACKER_LEAGUE_ID = "sleeper:1312118348556828672"


@pytest.fixture
def sleeper_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "draft-macker.db"))
    adp = pd.DataFrame(
        {
            "player_name": [f"Player {i}" for i in range(1, 41)],
            "position": (["RB", "WR", "TE", "QB"] * 10)[:40],
            "platform": ["fantasypros"] * 40,
            "adp": [float(i) for i in range(1, 41)],
            "adp_high": [float(i) - 1 for i in range(1, 41)],
            "adp_low": [float(i) + 1 for i in range(1, 41)],
        }
    )
    db.store_adp(adp, season=2026)
    yield db
    db.close()


@pytest.fixture
def client(sleeper_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(Config, "WEB_AUTH_ENABLED", False)
    league_data = {
        "league": {
            "league_id": MACKER_LEAGUE_ID,
            "provider": "sleeper",
            "name": "Tight ends and loose lips",
            "season": 2026,
            "num_teams": 10,
            "sleeper_league_id": "1312118348556828672",
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"],
            "scoring_settings": {"rec": 1.0},
        },
        "teams": [
            {
                "team_id": "sleeper:1312118348556828672:1",
                "name": "Macker Team",
                "owner": "macker1477",
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0,
                "points_against": 0,
                "rank": 1,
                "roster": [{"player": "Josh Allen", "position": "QB", "team": "BUF"}],
            },
            {
                "team_id": "sleeper:1312118348556828672:2",
                "name": "Other",
                "owner": "rival",
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
    sleeper_db.store_user_league("dev-user", league_data)
    app = create_sleeper_app(db_path=str(sleeper_db.db_path), require_auth=False)
    with TestClient(app) as test_client:
        yield test_client


def test_macker_snake_defaults():
    assert compute_snake_pick_slots(1, 10) == [1, 20, 21]


def test_macker_draft_help_pick_slots_and_board(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "ffpy.draft_strategy.load_sleeper_players",
        lambda force=False: {"p1": {"full_name": "Player One", "position": "RB", "team": "KC"}},
    )
    monkeypatch.setattr(
        "ffpy.sleeper_import.SleeperIntegration.get_rosters",
        lambda league_id: [
            {
                "roster_id": 1,
                "owner_id": "uid_macker",
                "settings": {"draft_slot": 1},
                "players": [],
            }
        ],
    )
    res = client.post(
        f"/api/leagues/{MACKER_LEAGUE_ID}/draft-help",
        json={
            "team_id": "sleeper:1312118348556828672:1",
            "pick_slots": [1, 20, 21],
            "num_teams": 10,
            "num_players": 10,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["picks"][0]["pick_slot"] == 1
    assert payload["picks"][1]["pick_slot"] == 20
    assert payload["picks"][2]["pick_slot"] == 21
    assert len(payload["rankings"]) == 10
    assert all(r.get("reasons") for r in payload["rankings"])
