"""Phase 1 tests: historical game retrieval + coverage audit + backtest schema.

Uses a fresh tmp_path SQLite DB for isolation. Seeds synthetic game rows
directly so tests don't depend on an nflverse load.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from ffpy.database import FFPyDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path) -> FFPyDatabase:
    """A brand-new DB in an isolated tmp path. Runs 001 + 003 via init_database."""
    db = FFPyDatabase(db_path=str(tmp_path / "test.db"))
    yield db
    db.close()


@pytest.fixture
def db_with_games(fresh_db: FFPyDatabase) -> FFPyDatabase:
    """DB with migration 002 (games table) plus a few seeded rows covering:

    - A fully-usable week (all games have spread + scores)
    - A partially-usable week (one game missing spread_line)
    - A tie game (equal scores)
    - A postseason game
    - An unfinished game (NULL scores)
    """
    fresh_db.run_migration("002_play_by_play_schema.sql")
    cur = fresh_db.conn.cursor()

    # 2022 REG week 1: 3 games, all have spread + scores (fully usable)
    cur.executemany(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        [
            ("2022_01_ARI_KC", 2022, "REG", 1, "2022-09-11", "KC", "ARI", 44, 21, -6.5, 54.0),
            ("2022_01_NYG_TEN", 2022, "REG", 1, "2022-09-11", "TEN", "NYG", 20, 21, -5.5, 43.5),
            ("2022_01_LAC_LV", 2022, "REG", 1, "2022-09-11", "LV", "LAC", 19, 24, -3.0, 52.5),
        ],
    )

    # 2022 REG week 2: one game missing spread_line → week is NOT fully usable
    cur.executemany(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        [
            ("2022_02_BUF_MIA", 2022, "REG", 2, "2022-09-18", "MIA", "BUF", 21, 19, 3.5, 53.0),
            (
                "2022_02_DAL_CIN",
                2022,
                "REG",
                2,
                "2022-09-18",
                "DAL",
                "CIN",
                20,
                17,
                None,
                45.0,
            ),  # missing spread
        ],
    )

    # 2022 REG week 3: tie game (same scores)
    cur.execute(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, 2022, 'REG', 3, '2022-09-25', 'NYG', 'IND', 20, 20, -3.0, 45.5, 1)""",
        ("2022_03_IND_NYG",),
    )

    # 2022 POST wildcard: one game (postseason is season_type='POST')
    cur.execute(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, 2022, 'POST', 1, '2023-01-14', 'SF', 'SEA', 41, 23, -10.0, 42.5, 1)""",
        ("2022_19_SEA_SF",),
    )

    # 2023 REG week 1: scheduled but unplayed (NULL scores)
    cur.execute(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, 2023, 'REG', 1, '2023-09-07', 'DET', 'KC', NULL, NULL, -4.5, 53.0, 0)""",
        ("2023_01_DET_KC",),
    )

    fresh_db.conn.commit()
    return fresh_db


# ---------------------------------------------------------------------------
# Migration 003 — backtest schema is created by init_database
# ---------------------------------------------------------------------------


class TestBacktestSchema:
    def test_backtest_runs_table_exists(self, fresh_db):
        row = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_runs'",
            fresh_db.conn,
        )
        assert len(row) == 1

    def test_backtest_picks_table_exists(self, fresh_db):
        row = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_picks'",
            fresh_db.conn,
        )
        assert len(row) == 1

    def test_init_database_is_idempotent(self, fresh_db):
        """Re-running init_database must not raise (CREATE TABLE IF NOT EXISTS)."""
        fresh_db.init_database()
        fresh_db.init_database()

    def test_backtest_runs_accepts_inserts(self, fresh_db):
        cur = fresh_db.conn.cursor()
        cur.execute(
            """INSERT INTO backtest_runs (strategy_name, strategy_params,
                   season_start, season_end, week_start, week_end, season_type,
                   total_games, correct, incorrect, ties,
                   confidence_earned, confidence_max)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AllFavorites", json.dumps({}), 2021, 2022, 1, 18, "REG", 500, 330, 165, 5, 6800, 9500),
        )
        run_id = cur.lastrowid
        fresh_db.conn.commit()

        cur.execute(
            """INSERT INTO backtest_picks (run_id, season, week, game_id,
                   selected_team, confidence, correct)
               VALUES (?, 2021, 1, '2021_01_NYJ_CAR', 'CAR', 12, 1)""",
            (run_id,),
        )
        fresh_db.conn.commit()

        runs = pd.read_sql("SELECT * FROM backtest_runs WHERE run_id = ?", fresh_db.conn, params=(run_id,))
        picks = pd.read_sql("SELECT * FROM backtest_picks WHERE run_id = ?", fresh_db.conn, params=(run_id,))
        assert len(runs) == 1 and runs.iloc[0]["strategy_name"] == "AllFavorites"
        assert len(picks) == 1 and picks.iloc[0]["selected_team"] == "CAR"


# ---------------------------------------------------------------------------
# get_historical_games
# ---------------------------------------------------------------------------


class TestGetHistoricalGames:
    def test_returns_season_by_default(self, db_with_games):
        df = db_with_games.get_historical_games(2022)
        assert set(df["season"]) == {2022}
        assert set(df["season_type"]) == {"REG"}  # REG is the default filter

    def test_filters_by_week(self, db_with_games):
        df = db_with_games.get_historical_games(2022, week=1)
        assert len(df) == 3
        assert (df["week"] == 1).all()

    def test_postseason_filter(self, db_with_games):
        reg = db_with_games.get_historical_games(2022, season_type="REG")
        post = db_with_games.get_historical_games(2022, season_type="POST")
        assert len(post) == 1 and post.iloc[0]["game_id"] == "2022_19_SEA_SF"
        assert "2022_19_SEA_SF" not in set(reg["game_id"])

    def test_unfinished_games_excluded_by_default(self, db_with_games):
        """finished_only=True (default) must drop rows with NULL scores."""
        df = db_with_games.get_historical_games(2023)
        assert df.empty  # the single 2023 row has NULL scores

    def test_unfinished_games_included_when_opted_in(self, db_with_games):
        df = db_with_games.get_historical_games(2023, finished_only=False)
        assert len(df) == 1
        assert pd.isna(df.iloc[0]["home_score"])

    def test_expected_columns_present(self, db_with_games):
        df = db_with_games.get_historical_games(2022, week=1)
        for col in (
            "game_id",
            "season",
            "season_type",
            "week",
            "game_date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "spread_line",
            "total_line",
            "roof",
            "surface",
            "temp",
            "wind",
        ):
            assert col in df.columns, f"missing column: {col}"

    def test_includes_rows_with_missing_spread(self, db_with_games):
        """Missing spread must not be silently dropped — it's the coverage
        auditor's job to flag those, not get_historical_games."""
        df = db_with_games.get_historical_games(2022, week=2)
        assert len(df) == 2
        assert df["spread_line"].isna().sum() == 1

    def test_includes_ties(self, db_with_games):
        df = db_with_games.get_historical_games(2022, week=3)
        row = df.iloc[0]
        assert row["home_score"] == row["away_score"]  # tie preserved

    def test_fails_clearly_when_games_table_missing(self, fresh_db):
        """If nflverse loader hasn't run, games table doesn't exist —
        we should raise an obvious OperationalError, not a silent empty."""
        with pytest.raises(Exception) as exc:
            fresh_db.get_historical_games(2022)
        assert "games" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# get_data_coverage
# ---------------------------------------------------------------------------


class TestGetDataCoverage:
    def test_returns_per_week_rows(self, db_with_games):
        df = db_with_games.get_data_coverage()
        # REG: weeks 1, 2, 3 of 2022 (week of unfinished 2023 also included)
        assert set(df["week"]) >= {1, 2, 3}

    def test_fully_usable_flag(self, db_with_games):
        df = db_with_games.get_data_coverage()
        week_idx = df.set_index(["season", "week"])

        # 2022 week 1: 3 games, all have spread + scores → fully usable
        assert week_idx.loc[(2022, 1), "fully_usable"] == 1
        # 2022 week 2: one game missing spread → NOT fully usable
        assert week_idx.loc[(2022, 2), "fully_usable"] == 0

    def test_pct_with_spread(self, db_with_games):
        df = db_with_games.get_data_coverage()
        week_idx = df.set_index(["season", "week"])
        assert week_idx.loc[(2022, 1), "pct_with_spread"] == 100.0
        assert week_idx.loc[(2022, 2), "pct_with_spread"] == 50.0

    def test_season_range_filter(self, db_with_games):
        df = db_with_games.get_data_coverage(season_start=2022, season_end=2022)
        assert set(df["season"]) == {2022}

    def test_season_type_filter(self, db_with_games):
        reg = db_with_games.get_data_coverage(season_type="REG")
        post = db_with_games.get_data_coverage(season_type="POST")
        assert not reg.empty and not post.empty
        # POST wk 1 has just 1 game
        post_idx = post.set_index(["season", "week"])
        assert post_idx.loc[(2022, 1), "n_games"] == 1

    def test_handles_empty_window(self, db_with_games):
        df = db_with_games.get_data_coverage(season_start=1999, season_end=2000)
        assert df.empty
