"""Tests for CFB projection models."""

from __future__ import annotations

import pandas as pd
import pytest

from ffpy.cfb_projections import CfbProjectionModel
from ffpy.database import FFPyDatabase


@pytest.fixture()
def projection_db(tmp_path):
    db = FFPyDatabase(str(tmp_path / "proj.db"))
    db.store_cfb_teams(
        pd.DataFrame(
            [
                {"team_key": "alabama", "season": 2024, "school": "Alabama", "conference": "SEC"},
                {"team_key": "auburn", "season": 2024, "school": "Auburn", "conference": "SEC"},
            ]
        )
    )
    db.store_cfb_players(
        pd.DataFrame(
            [
                {
                    "season": 2024,
                    "full_name": "Player A",
                    "position": "QB",
                    "team_key": "alabama",
                    "conference": "SEC",
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                },
                {
                    "season": 2024,
                    "full_name": "Player B",
                    "position": "QB",
                    "team_key": "auburn",
                    "conference": "SEC",
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                },
            ]
        ),
        season=2024,
    )
    players = db.get_cfb_players(season=2024)
    pid_a = int(players.iloc[0]["player_id"])
    pid_b = int(players.iloc[1]["player_id"])

    db.store_cfb_fantasy_points(
        pd.DataFrame(
            [
                {
                    "player_id": pid_a,
                    "season": 2023,
                    "week": 1,
                    "scoring_preset": "college_standard",
                    "actual_points": 20.0,
                    "conference_eligible": 1,
                },
                {
                    "player_id": pid_a,
                    "season": 2023,
                    "week": 2,
                    "scoring_preset": "college_standard",
                    "actual_points": 24.0,
                    "conference_eligible": 1,
                },
            ]
        )
    )
    db.store_cfb_fantasy_points(
        pd.DataFrame(
            [
                {
                    "player_id": pid_a,
                    "season": 2024,
                    "week": 1,
                    "scoring_preset": "college_standard",
                    "actual_points": 18.0,
                    "conference_eligible": 1,
                },
                {
                    "player_id": pid_a,
                    "season": 2024,
                    "week": 2,
                    "scoring_preset": "college_standard",
                    "actual_points": 22.0,
                    "conference_eligible": 1,
                },
                {
                    "player_id": pid_b,
                    "season": 2024,
                    "week": 1,
                    "scoring_preset": "college_standard",
                    "actual_points": 10.0,
                    "conference_eligible": 1,
                },
                {
                    "player_id": pid_b,
                    "season": 2024,
                    "week": 2,
                    "scoring_preset": "college_standard",
                    "actual_points": 12.0,
                    "conference_eligible": 1,
                },
            ]
        )
    )
    db.conn.executemany(
        """INSERT INTO cfb_games (game_id, season, week, home_team, away_team)
           VALUES (?, ?, ?, ?, ?)""",
        [("g1", 2024, 3, "Alabama", "Auburn")],
    )
    db.conn.commit()
    db.store_cfb_team_defense_stats(
        pd.DataFrame(
            [
                {
                    "team_key": "auburn",
                    "cfbd_game_id": 1,
                    "season": 2024,
                    "week": 1,
                    "points_allowed": 35.0,
                },
                {
                    "team_key": "alabama",
                    "cfbd_game_id": 2,
                    "season": 2024,
                    "week": 1,
                    "points_allowed": 14.0,
                },
            ]
        )
    )
    db.close()
    return str(tmp_path / "proj.db"), pid_a, pid_b


def test_week1_uses_prior_season_blend(projection_db):
    db_path, pid_a, _ = projection_db
    db = FFPyDatabase(db_path)
    with CfbProjectionModel(db) as model:
        out = model.generate_projections(2024, week=1, conferences=["SEC"], model="historical")
    assert not out.empty
    row = out[out["player_id"] == pid_a].iloc[0]
    assert row["projected_points"] >= 20.0


def test_opponent_adj_differs_from_historical(projection_db):
    db_path, pid_a, _ = projection_db
    db = FFPyDatabase(db_path)
    with CfbProjectionModel(db) as model:
        hist = model.generate_projections(2024, week=3, conferences=["SEC"], model="historical")
        opp = model.generate_projections(2024, week=3, conferences=["SEC"], model="opponent_adj")
    h = float(hist[hist["player_id"] == pid_a]["projected_points"].iloc[0])
    o = float(opp[opp["player_id"] == pid_a]["projected_points"].iloc[0])
    assert o > h


def test_both_models_coexist(projection_db):
    db_path, pid_a, _ = projection_db
    db = FFPyDatabase(db_path)
    with CfbProjectionModel(db) as model:
        model.generate_projections(2024, week=3, conferences=["SEC"], model="historical")
        model.generate_projections(2024, week=3, conferences=["SEC"], model="opponent_adj")
    hist = db.get_cfb_projections(2024, 3, model="historical")
    opp = db.get_cfb_projections(2024, 3, model="opponent_adj")
    assert len(hist) >= 1
    assert len(opp) >= 1
    db.close()
