"""Tests for CFB league API endpoints."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ffpy.database import FFPyDatabase
from ffpy.league_api import create_league_app


def _seed_league_db(db_path):
    db = FFPyDatabase(str(db_path))
    db.store_cfb_teams(
        pd.DataFrame(
            [
                {
                    "team_key": "alabama",
                    "season": 2024,
                    "school": "Alabama",
                    "conference": "SEC",
                    "abbreviation": "ALA",
                },
                {
                    "team_key": "georgia",
                    "season": 2024,
                    "school": "Georgia",
                    "conference": "SEC",
                    "abbreviation": "UGA",
                },
            ]
        )
    )
    db.store_cfb_players(
        pd.DataFrame(
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
                },
                {
                    "season": 2024,
                    "full_name": "Carson Beck",
                    "position": "QB",
                    "team_key": "georgia",
                    "conference": "SEC",
                    "cfbd_athlete_id": 4432580,
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                },
                {
                    "season": 2024,
                    "full_name": "Big Ten QB",
                    "position": "QB",
                    "team_key": "ohio_state",
                    "conference": "Big Ten",
                    "cfbd_athlete_id": 999,
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                },
            ]
        ),
        season=2024,
    )
    players = db.get_cfb_players(season=2024)
    pids = {row["full_name"]: int(row["player_id"]) for _, row in players.iterrows()}
    for pid in pids.values():
        db.store_cfb_projections(
            pd.DataFrame(
                [
                    {
                        "player_id": pid,
                        "season": 2024,
                        "week": 1,
                        "model": "historical",
                        "projected_points": 20.0,
                    },
                    {
                        "player_id": pid,
                        "season": 2024,
                        "week": 2,
                        "model": "historical",
                        "projected_points": 21.0,
                    },
                ]
            )
        )
    db.close()
    return pids


@pytest.fixture()
def cfb_api_db(tmp_path):
    db_path = tmp_path / "cfb-league.db"
    pids = _seed_league_db(db_path)
    return db_path, pids


@pytest.fixture()
def cfb_client(cfb_api_db):
    db_path, _ = cfb_api_db
    app = create_league_app(db_path=str(db_path), require_auth=False)
    return TestClient(app)


def test_create_cfb_league_and_player_pool(cfb_client, cfb_api_db):
    _, pids = cfb_api_db
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
    assert len(players) >= 2
    assert any(p["player_id"] == pids["Jalen Milroe"] for p in players)


def test_cfb_lineup_and_scores(cfb_client, cfb_api_db):
    db_path, pids = cfb_api_db
    pid = pids["Jalen Milroe"]
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

    db = FFPyDatabase(str(db_path))
    db.store_cfb_fantasy_points(
        pd.DataFrame(
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


def test_roster_add_drop_and_ineligible(cfb_client, cfb_api_db):
    _, pids = cfb_api_db
    league_id = cfb_client.post(
        "/api/cfb/leagues",
        json={"name": "Roster League", "season": 2024, "allowed_conferences": ["SEC"]},
    ).json()["league_id"]
    team_id = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams",
        json={"team_name": "Team A"},
    ).json()["league_team_id"]

    ok = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams/{team_id}/roster",
        json={"add": [pids["Jalen Milroe"]], "drop": []},
    )
    assert ok.status_code == 200
    assert len(ok.json()["roster"]) == 1

    bad = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams/{team_id}/roster",
        json={"add": [pids["Big Ten QB"]], "drop": []},
    )
    assert bad.status_code == 400

    pool = cfb_client.get(
        f"/api/cfb/leagues/{league_id}/player-pool",
        params={"week": 1, "available_only": True},
    )
    available_ids = {p["player_id"] for p in pool.json()["players"]}
    assert pids["Jalen Milroe"] not in available_ids


def test_standings_after_two_weeks(cfb_client, cfb_api_db):
    db_path, pids = cfb_api_db
    pid = pids["Jalen Milroe"]
    league_id = cfb_client.post(
        "/api/cfb/leagues",
        json={"name": "Standings League", "season": 2024},
    ).json()["league_id"]
    team_id = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams",
        json={"team_name": "Points Team"},
    ).json()["league_team_id"]

    db = FFPyDatabase(str(db_path))
    db.store_cfb_fantasy_points(
        pd.DataFrame(
            [
                {
                    "player_id": pid,
                    "season": 2024,
                    "week": 1,
                    "scoring_preset": "college_standard",
                    "actual_points": 25.0,
                    "conference_eligible": 1,
                },
                {
                    "player_id": pid,
                    "season": 2024,
                    "week": 2,
                    "scoring_preset": "college_standard",
                    "actual_points": 15.0,
                    "conference_eligible": 1,
                },
            ]
        )
    )
    db.close()

    for week in (1, 2):
        cfb_client.post(
            f"/api/cfb/leagues/{league_id}/teams/{team_id}/lineup",
            json={
                "season": 2024,
                "week": week,
                "entries": [{"player_id": pid, "slot": "QB", "is_starter": True}],
            },
        )

    standings = cfb_client.get(f"/api/cfb/leagues/{league_id}/standings", params={"through_week": 2})
    assert standings.status_code == 200
    assert standings.json()["standings"][0]["points_for"] == 40.0


def test_matchups_generate_and_score(cfb_client, cfb_api_db):
    db_path, pids = cfb_api_db
    league_id = cfb_client.post(
        "/api/cfb/leagues",
        json={"name": "H2H League", "season": 2024, "num_teams": 4},
    ).json()["league_id"]
    teams = []
    for name, player in [("Team A", "Jalen Milroe"), ("Team B", "Carson Beck")]:
        tid = cfb_client.post(
            f"/api/cfb/leagues/{league_id}/teams",
            json={"team_name": name},
        ).json()["league_team_id"]
        cfb_client.post(
            f"/api/cfb/leagues/{league_id}/teams/{tid}/roster",
            json={"add": [pids[player]], "drop": []},
        )
        teams.append((tid, pids[player]))

    db = FFPyDatabase(str(db_path))
    for tid, pid in teams[:2]:
        db.store_cfb_fantasy_points(
            pd.DataFrame(
                [
                    {
                        "player_id": pid,
                        "season": 2024,
                        "week": 1,
                        "scoring_preset": "college_standard",
                        "actual_points": 30.0 if pid == pids["Jalen Milroe"] else 10.0,
                        "conference_eligible": 1,
                    }
                ]
            )
        )
    db.close()

    gen = cfb_client.post(f"/api/cfb/leagues/{league_id}/weeks/1/matchups/generate")
    assert gen.status_code == 200
    assert gen.json()["count"] >= 1

    for tid, pid in teams[:2]:
        cfb_client.post(
            f"/api/cfb/leagues/{league_id}/teams/{tid}/lineup",
            json={
                "season": 2024,
                "week": 1,
                "entries": [{"player_id": pid, "slot": "QB", "is_starter": True}],
            },
        )

    scored = cfb_client.post(f"/api/cfb/leagues/{league_id}/weeks/1/matchups/score")
    assert scored.status_code == 200
    matchup = scored.json()["matchups"][0]
    assert matchup["home_score"] is not None
    assert matchup["away_score"] is not None


def test_cfb_transaction_stub(cfb_client, cfb_api_db):
    _, pids = cfb_api_db
    league_id = cfb_client.post(
        "/api/cfb/leagues",
        json={"name": "Tx League", "season": 2024},
    ).json()["league_id"]
    team_id = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/teams",
        json={"team_name": "Tx Team"},
    ).json()["league_team_id"]

    create = cfb_client.post(
        f"/api/cfb/leagues/{league_id}/transactions",
        json={
            "league_team_id": team_id,
            "tx_type": "add",
            "player_id": pids["Jalen Milroe"],
            "faab_bid": 5.0,
            "week": 1,
        },
    )
    assert create.status_code == 200
    assert create.json()["status"] == "pending"

    listed = cfb_client.get(f"/api/cfb/leagues/{league_id}/transactions")
    assert listed.status_code == 200
    assert len(listed.json()["transactions"]) == 1
