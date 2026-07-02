"""Tests for CFB league API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ffpy.database import FFPyDatabase
from ffpy.league_api import create_league_app


@pytest.fixture()
def cfb_api_db(tmp_path):
    db_path = tmp_path / "cfb-league.db"
    db = FFPyDatabase(str(db_path))
    db.store_cfb_teams(
        __import__("pandas").DataFrame(
            [
                {
                    "team_key": "alabama",
                    "season": 2024,
                    "school": "Alabama",
                    "conference": "SEC",
                    "abbreviation": "ALA",
                }
            ]
        )
    )
    db.store_cfb_players(
        __import__("pandas").DataFrame(
            [
                {
                    "season": 2024,
                    "full_name": "Jalen Milroe",
                    "position": "QB",
                    "team_key": "alabama",
                    "conference": "SEC",
                    "cfbd_athlete_id": 4432577,
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                }
            ]
        ),
        season=2024,
    )
    players = db.get_cfb_players(season=2024)
    pid = int(players.iloc[0]["player_id"])
    db.store_cfb_projections(
        __import__("pandas").DataFrame(
            [
                {
                    "player_id": pid,
                    "season": 2024,
                    "week": 1,
                    "model": "historical",
                    "projected_points": 22.5,
                }
            ]
        )
    )
    db.close()
    return db_path, pid


@pytest.fixture()
def cfb_client(cfb_api_db):
    db_path, _ = cfb_api_db
    app = create_league_app(db_path=str(db_path), require_auth=False)
    return TestClient(app)


def test_create_cfb_league_and_player_pool(cfb_client, cfb_api_db):
    _, pid = cfb_api_db
    resp = cfb_client.post(
        "/api/cfb/leagues",
        json={
            "name": "SEC Test League",
            "season": 2024,
            "allowed_conferences": ["SEC", "Big Ten", "ACC"],
        },
    )
    assert resp.status_code == 200
    league_id = resp.json()["league_id"]

    pool = cfb_client.get(f"/api/cfb/leagues/{league_id}/player-pool", params={"week": 1})
    assert pool.status_code == 200
    players = pool.json()["players"]
    assert len(players) >= 1
    assert any(p["player_id"] == pid for p in players)


def test_cfb_lineup_and_scores(cfb_client, cfb_api_db):
    _, pid = cfb_api_db
    league = cfb_client.post(
        "/api/cfb/leagues",
        json={"name": "Lineup League", "season": 2024},
    ).json()
    league_id = league["league_id"]

    team = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams",
        json={"team_name": "Test Team", "owner_name": "Owner"},
    ).json()
    team_id = team["league_team_id"]

    db = FFPyDatabase(str(cfb_api_db[0]))
    db.store_cfb_fantasy_points(
        __import__("pandas").DataFrame(
            [
                {
                    "player_id": pid,
                    "season": 2024,
                    "week": 1,
                    "scoring_preset": "college_standard",
                    "actual_points": 30.0,
                    "conference_eligible": 1,
                }
            ]
        )
    )
    db.close()

    lineup_resp = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams/{team_id}/lineup",
        json={
            "season": 2024,
            "week": 1,
            "entries": [{"player_id": pid, "slot": "QB", "is_starter": True}],
        },
    )
    assert lineup_resp.status_code == 200

    scores = cfb_client.get(f"/api/cfb/leagues/{league_id}/weeks/1/scores")
    assert scores.status_code == 200
    teams = scores.json()["teams"]
    assert teams[0]["points"] == 30.0
