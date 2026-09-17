"""Tests for the ffpy-db command-line interface."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from ffpy import cli
from ffpy.config import Config


def _count_rows(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_prepare_mock_generates_required_app_data(tmp_path: Path):
    db_path = tmp_path / "app-data.db"
    args = [
        "prepare",
        "--mock",
        "--season",
        "2024",
        "--start-week",
        "1",
        "--end-week",
        "2",
        "--db-path",
        str(db_path),
        "--quiet",
    ]

    assert cli.main(args) == 0

    assert _count_rows(db_path, "actual_stats") == 80
    assert _count_rows(db_path, "games") == 32

    # The default app-data command should be safe to run repeatedly.
    assert cli.main(args) == 0

    assert _count_rows(db_path, "actual_stats") == 80
    assert _count_rows(db_path, "games") == 32


def test_prepare_parser_defaults_to_real_data_mode():
    parser = cli.build_parser()
    args = parser.parse_args(["prepare"])

    assert args.command == "prepare"
    assert args.mock is False
    assert args.season == Config.NFL_SEASON
    assert args.stats_source == "nflverse"


def test_normalise_nflverse_actual_stats_maps_required_columns():
    raw = pd.DataFrame(
        [
            {
                "player_id": "00-123",
                "player_display_name": "Example QB",
                "position": "QB",
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "team": "KC",
                "opponent_team": "BAL",
                "passing_yards": 250,
                "passing_tds": 2,
                "passing_interceptions": 1,
                "rushing_yards": 12,
                "rushing_tds": 0,
                "receiving_yards": 0,
                "receiving_tds": 0,
                "receptions": 0,
                "fantasy_points_ppr": 21.2,
            },
            {
                "player_id": "00-456",
                "player_display_name": "Example K",
                "position": "K",
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "team": "KC",
                "opponent_team": "BAL",
                "fantasy_points_ppr": 0.0,
                "fg_made": 2,
                "fg_att": 2,
                "fg_missed": 0,
                "fg_blocked": 0,
                "fg_long": 45,
                "fg_made_0_19": 0,
                "fg_made_20_29": 1,
                "fg_made_30_39": 0,
                "fg_made_40_49": 1,
                "fg_made_50_59": 0,
                "fg_made_60_": 0,
                "pat_made": 2,
                "pat_att": 2,
            },
        ]
    )

    out = cli._normalise_nflverse_actual_stats(raw, season=2024, start_week=1, end_week=1)

    assert len(out) == 2
    row = out[out["position"] == "QB"].iloc[0]
    assert row["player"] == "Example QB"
    assert row["team"] == "KC"
    assert row["opponent"] == "BAL"
    assert row["actual_points"] == 21.2
    assert row["interceptions"] == 1
    assert row["nfl_id"] == "00-123"

    # Kickers are kept and scored from kicking stats (nflverse fantasy points
    # are always 0.0 for K): 3 (20-29) + 4 (40-49) + 2 XP = 9.0.
    kicker = out[out["position"] == "K"].iloc[0]
    assert kicker["player"] == "Example K"
    assert kicker["actual_points"] == 9.0
    assert kicker["fg_made"] == 2
    assert kicker["fgm_40_49"] == 1
    assert kicker["xp_made"] == 2
