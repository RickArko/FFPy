"""Tests for college football data loading and normalization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from ffpy.cfbverse import (
    cfb_roster_availability_message,
    extract_cfb_games_from_pbp,
    normalize_cfb_plays,
    normalize_cfb_rosters,
    normalize_cfb_schedule,
    position_from_id,
)
from ffpy.database import FFPyDatabase


def test_normalize_cfb_schedule_maps_espn_columns():
    raw = pd.DataFrame(
        [
            {
                "game_id": 401628579,
                "season": 2024,
                "week": 1,
                "season_type": 2,
                "game_date": "2024-08-29T23:00Z",
                "neutral_site": False,
                "conference_competition": True,
                "home_id": 48,
                "away_id": 2803,
                "home_team": "Delaware Blue Hens",
                "away_team": "Bryant Bulldogs",
                "home_abbreviation": "DEL",
                "away_abbreviation": "BRY",
                "home_score": 48,
                "away_score": 17,
                "home_winner": True,
                "away_winner": False,
                "venue": "Delaware Stadium",
                "attendance": 12000,
                "status": "STATUS_FINAL",
            }
        ]
    )

    out = normalize_cfb_schedule(raw)
    row = out.iloc[0]
    assert row["game_id"] == "401628579"
    assert row["season"] == 2024
    assert row["home_abbreviation"] == "DEL"
    assert row["conference_game"] == 1
    assert row["game_finished"] == 1


def test_extract_cfb_games_from_pbp_derives_final_scores():
    raw = pd.DataFrame(
        [
            {
                "game_id": 100,
                "year": 2023,
                "week": 5,
                "game_play_number": 1,
                "home": "Alabama",
                "away": "Auburn",
                "pos_team": "Alabama",
                "pos_team_score": 7,
                "def_pos_team_score": 0,
            },
            {
                "game_id": 100,
                "year": 2023,
                "week": 5,
                "game_play_number": 2,
                "home": "Alabama",
                "away": "Auburn",
                "pos_team": "Auburn",
                "pos_team_score": 10,
                "def_pos_team_score": 7,
            },
            {
                "game_id": 100,
                "year": 2023,
                "week": 5,
                "game_play_number": 3,
                "home": "Alabama",
                "away": "Auburn",
                "pos_team": "Alabama",
                "pos_team_score": 14,
                "def_pos_team_score": 10,
            },
        ]
    )

    out = extract_cfb_games_from_pbp(raw)
    row = out.iloc[0]
    assert row["game_id"] == "100"
    assert row["home_score"] == 14
    assert row["away_score"] == 10
    assert row["game_finished"] == 1


def test_normalize_cfb_rosters_extracts_position_id():
    raw = pd.DataFrame(
        [
            {
                "season": 2024,
                "team_id": 333,
                "athlete_id": 504059,
                "athlete_uid": "s:20~l:23~a:504059",
                "full_name": "Jay Williams",
                "first_name": "Jay",
                "last_name": "Williams",
                "position_href": "http://sports.core.api.espn.com/v2/sports/football/leagues/college-football/positions/17?lang=en",
                "team_abbreviation": "ALA",
                "team_name": "Crimson Tide",
                "active": True,
            }
        ]
    )

    out = normalize_cfb_rosters(raw)
    row = out.iloc[0]
    assert row["position_id"] == "17"
    assert row["full_name"] == "Jay Williams"
    assert row["active"] == 1


def test_normalize_cfb_plays_renames_key_columns():
    raw = pd.DataFrame(
        [
            {
                "id_play": 1,
                "game_id": 401,
                "year": 2024,
                "week": 1,
                "play_type": "Pass Reception",
                "play_text": "Example pass",
                "EPA": 1.2,
                "home": "Alabama",
                "away": "Georgia",
            }
        ]
    )

    out = normalize_cfb_plays(raw)
    row = out.iloc[0]
    assert row["play_id"] == "1"
    assert row["game_id"] == "401"
    assert row["season"] == 2024
    assert row["epa"] == 1.2
    assert row["home_team"] == "Alabama"


def test_cfb_roster_availability_message_for_unpublished_season():
    message = cfb_roster_availability_message(2025)
    assert message is not None
    assert "2025" in message
    assert "--skip-rosters" in message


def test_cfb_roster_availability_message_for_published_season():
    assert cfb_roster_availability_message(2024) is None
    assert position_from_id("17") == "QB"
    assert position_from_id("45") == "WR"
    assert position_from_id("999") is None


def test_cfb_database_roundtrip(tmp_path: Path):
    db_path = tmp_path / "cfb.db"
    db = FFPyDatabase(str(db_path))
    try:
        games = normalize_cfb_schedule(
            pd.DataFrame(
                [
                    {
                        "game_id": 1,
                        "season": 2024,
                        "week": 1,
                        "season_type": 2,
                        "game_date": "2024-09-01",
                        "neutral_site": False,
                        "conference_competition": False,
                        "home_team": "Team A",
                        "away_team": "Team B",
                        "home_abbreviation": "A",
                        "away_abbreviation": "B",
                        "home_score": 21,
                        "away_score": 14,
                        "home_winner": True,
                        "away_winner": False,
                        "status": "STATUS_FINAL",
                    }
                ]
            )
        )
        assert db.store_cfb_games(games) == 1

        rosters = normalize_cfb_rosters(
            pd.DataFrame(
                [
                    {
                        "season": 2024,
                        "team_id": 1,
                        "athlete_id": 99,
                        "full_name": "Test Player",
                        "team_abbreviation": "A",
                        "active": True,
                    }
                ]
            )
        )
        assert db.store_cfb_rosters(rosters, season=2024) >= 1

        plays = normalize_cfb_plays(
            pd.DataFrame(
                [
                    {
                        "id_play": 10,
                        "game_id": 1,
                        "year": 2024,
                        "week": 1,
                        "play_type": "Rush",
                        "EPA": 0.5,
                        "home": "Team A",
                        "away": "Team B",
                    }
                ]
            )
        )
        assert db.store_cfb_plays(plays, show_progress=False) == 1

        assert len(db.get_cfb_games(season=2024)) == 1
        assert len(db.get_cfb_rosters(season=2024)) == 1
        assert len(db.get_cfb_plays(season=2024)) == 1

        conn = sqlite3.connect(db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cfb_%'"
                )
            }
        finally:
            conn.close()
        assert {"cfb_games", "cfb_rosters", "cfb_plays"}.issubset(tables)
        assert "cfb_teams" in tables
        assert "cfb_players" in tables
    finally:
        db.close()
