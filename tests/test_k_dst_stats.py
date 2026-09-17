"""Tests for kicker + DST scoring and DST weekly derivation."""

from __future__ import annotations

import pandas as pd

from ffpy.dst_stats import build_dst_weekly_rows, normalize_games_frame
from ffpy.scoring import (
    DST_DEFAULT_SCORING,
    KICKER_DEFAULT_SCORING,
    points_allowed_tier,
    score_dst_week,
    score_kicker_week,
)


class TestKickerScoring:
    def test_standard_buckets_and_pat(self):
        # 3 (20-29) + 4 (40-49) + 5 (50-59) + 2 XP = 14
        stats = {
            "fgm_20_29": 1,
            "fgm_40_49": 1,
            "fgm_50_59": 1,
            "fg_missed": 0,
            "xp_made": 2,
            "xp_att": 2,
        }
        assert score_kicker_week(stats) == 14.0

    def test_misses_and_xp_miss_penalized(self):
        # 3 (0-19) - 1 (fg miss) + 1 XP - 1 (xp miss) = 2
        stats = {
            "fgm_0_19": 1,
            "fg_missed": 1,
            "xp_made": 1,
            "xp_att": 2,
        }
        assert score_kicker_week(stats) == 2.0

    def test_sleeper_settings_override(self):
        settings = dict(KICKER_DEFAULT_SCORING)
        settings["fgm_50_59"] = 6.0
        settings["fgmiss"] = -2.0
        stats = {"fgm_50_59": 2, "fg_missed": 1, "xp_made": 0, "xp_att": 0}
        assert score_kicker_week(stats, settings) == 10.0

    def test_empty_week_scores_zero(self):
        assert score_kicker_week({}) == 0.0


class TestDstScoring:
    def test_shutout_with_turnovers(self):
        # 10 (shutout) + 2 sacks + 2 INT + 1 FR + 1 def TD = 10+2+4+2+6 = 24
        stats = {
            "points_allowed": 0,
            "sacks": 2,
            "def_interceptions": 2,
            "fumble_recoveries": 1,
            "def_tds": 1,
        }
        assert score_dst_week(stats) == 24.0

    def test_points_allowed_tiers(self):
        assert points_allowed_tier(0) == "pts_allow_0"
        assert points_allowed_tier(6) == "pts_allow_1_6"
        assert points_allowed_tier(13) == "pts_allow_7_13"
        assert points_allowed_tier(20) == "pts_allow_14_20"
        assert points_allowed_tier(27) == "pts_allow_21_27"
        assert points_allowed_tier(34) == "pts_allow_28_34"
        assert points_allowed_tier(35) == "pts_allow_35p"
        assert score_dst_week({"points_allowed": 35}) == -4.0
        assert score_dst_week({"points_allowed": 21}) == 0.0

    def test_missing_points_allowed_skips_tier(self):
        assert score_dst_week({"sacks": 3}) == 3.0

    def test_sleeper_settings_override(self):
        settings = dict(DST_DEFAULT_SCORING)
        settings["sack"] = 2.0
        assert score_dst_week({"sacks": 2, "points_allowed": 10}, settings) == 8.0


def _games_frame():
    return pd.DataFrame(
        [
            {
                "week": 1,
                "season_type": "REG",
                "home_team": "KC",
                "away_team": "BAL",
                "home_score": 27,
                "away_score": 20,
            },
            {
                "week": 1,
                "season_type": "REG",
                "home_team": "SF",
                "away_team": "NYJ",
                "home_score": 32,
                "away_score": 19,
            },
        ]
    )


def _stats_frame():
    # Defensive counting stats live on individual defensive players.
    return pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "season_type": "REG",
                "team": "KC",
                "def_sacks": 3,
                "def_interceptions": 1,
                "fumble_recovery_opp": 1,
                "def_tds": 1,
                "def_safeties": 0,
                "special_teams_tds": 0,
                "pt_return_tds": 0,
                "def_punt_blocks": 0,
                "def_fg_blocks": 1,
                "def_pat_blocks": 0,
            },
            {
                "season": 2025,
                "week": 1,
                "season_type": "REG",
                "team": "KC",
                "def_sacks": 1,
                "def_interceptions": 0,
                "fumble_recovery_opp": 0,
                "def_tds": 0,
                "def_safeties": 0,
                "special_teams_tds": 0,
                "pt_return_tds": 0,
                "def_punt_blocks": 0,
                "def_fg_blocks": 0,
                "def_pat_blocks": 0,
            },
            {
                "season": 2025,
                "week": 1,
                "season_type": "REG",
                "team": "SF",
                "def_sacks": 2,
                "def_interceptions": 2,
                "fumble_recovery_opp": 0,
                "def_tds": 0,
                "def_safeties": 1,
                "special_teams_tds": 1,
                "pt_return_tds": 0,
                "def_punt_blocks": 0,
                "def_fg_blocks": 0,
                "def_pat_blocks": 0,
            },
        ]
    )


class TestBuildDstWeeklyRows:
    def test_synthetic_identity_and_scoring(self):
        out = build_dst_weekly_rows(_stats_frame(), _games_frame(), season=2025, start_week=1, end_week=1)
        assert len(out) == 4  # 2 games × 2 teams
        kc = out[out["team"] == "KC"].iloc[0]
        assert kc["player"] == "Kansas City Chiefs"  # matches Sleeper DEF full_name
        assert kc["nfl_id"] == "dst:KC"
        assert kc["position"] == "DST"
        assert kc["opponent"] == "BAL"
        assert kc["home_away"] == "home"
        assert kc["points_allowed"] == 20
        # KC: 4 sacks + 1 INT + 1 FR + 1 def TD + 1 blk kick + pts_allow_14_20 (1)
        # = 4 + 2 + 2 + 6 + 4 + 1 = 19
        assert kc["actual_points"] == 19.0
        # SF (home): 2 sacks + 2 INT + 1 safety + 1 ST TD + pts_allow_14_20 (1)
        # = 2 + 4 + 2 + 6 + 1 = 15
        sf = out[out["team"] == "SF"].iloc[0]
        assert sf["actual_points"] == 15.0
        assert sf["home_away"] == "home"
        assert sf["points_allowed"] == 19

    def test_team_aliases_normalized(self):
        games = _games_frame()
        games.loc[0, "home_team"] = "LA"
        stats = _stats_frame()
        stats.loc[stats["team"] == "KC", "team"] = "LAR"  # unused alias target check
        out = build_dst_weekly_rows(stats, games, season=2025, start_week=1, end_week=1)
        assert "Los Angeles Rams" in set(out["player"])

    def test_unplayed_games_skipped(self):
        games = _games_frame()
        games["home_score"] = None
        games["away_score"] = None
        out = build_dst_weekly_rows(_stats_frame(), games, season=2025, start_week=1, end_week=1)
        assert out.empty

    def test_empty_inputs(self):
        out = build_dst_weekly_rows(pd.DataFrame(), pd.DataFrame(), season=2025, start_week=1, end_week=1)
        assert out.empty

    def test_punt_return_td_not_double_counted(self):
        """pt_return_tds is credited to the PUNTING team — never add it."""
        stats = _stats_frame()
        # WAS returner scores a punt-return TD; NO's punter is charged with pt_return_tds.
        returner = {col: 0 for col in stats.columns}
        returner.update(
            {"season": 2025, "week": 1, "season_type": "REG", "team": "WAS", "special_teams_tds": 1}
        )
        punter = {col: 0 for col in stats.columns}
        punter.update({"season": 2025, "week": 1, "season_type": "REG", "team": "NO", "pt_return_tds": 1})
        stats = pd.concat([stats, pd.DataFrame([returner, punter])], ignore_index=True)
        games = pd.DataFrame(
            [
                {
                    "week": 1,
                    "season_type": "REG",
                    "home_team": "NO",
                    "away_team": "WAS",
                    "home_score": 17,
                    "away_score": 24,
                }
            ]
        )
        out = build_dst_weekly_rows(stats, games, season=2025, start_week=1, end_week=1)
        was = out[out["team"] == "WAS"].iloc[0]
        no = out[out["team"] == "NO"].iloc[0]
        assert was["special_teams_tds"] == 1  # return team's DST gets the TD
        assert no["special_teams_tds"] == 0  # punting team's DST does NOT
        # WAS allowed 17 but NO's score includes no def/ST TDs → unchanged.
        assert was["points_allowed"] == 17

    def test_points_allowed_excludes_opponent_def_and_st_tds(self):
        """Sleeper DST points allowed excludes pick-sixes and return TDs (XP counts)."""
        stats = _stats_frame()
        # BAL's defense scores a pick-six against KC.
        bal_def = {col: 0 for col in stats.columns}
        bal_def.update({"season": 2025, "week": 1, "season_type": "REG", "team": "BAL", "def_tds": 1})
        stats = pd.concat([stats, pd.DataFrame([bal_def])], ignore_index=True)
        out = build_dst_weekly_rows(stats, _games_frame(), season=2025, start_week=1, end_week=1)
        kc = out[out["team"] == "KC"].iloc[0]
        # BAL scored 20, one pick-six → KC's DST is charged 14, not 20.
        assert kc["points_allowed"] == 14
        # BAL's own row still gets the defensive TD; KC's 27 included a
        # defensive TD (fixture def_tds=1), so BAL is charged 21.
        bal = out[out["team"] == "BAL"].iloc[0]
        assert bal["def_tds"] == 1
        assert bal["points_allowed"] == 21


class TestNormalizeGamesFrame:
    def test_nflverse_schedule_shape(self):
        sched = pd.DataFrame(
            [
                {
                    "week": 2,
                    "game_type": "REG",
                    "home_team": "DAL",
                    "away_team": "NYG",
                    "home_score": 24,
                    "away_score": 17,
                },
                {
                    "week": 2,
                    "game_type": "POST",
                    "home_team": "PHI",
                    "away_team": "GB",
                    "home_score": 30,
                    "away_score": 13,
                },
            ]
        )
        out = normalize_games_frame(sched)
        assert len(out) == 1  # POST filtered out
        assert out.iloc[0]["home_team"] == "DAL"


def test_store_dst_rows_round_trip(tmp_path):
    """Synthetic DST rows persist through store_actual_stats with new columns."""
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(db_path=str(tmp_path / "dst.db"))
    try:
        rows = build_dst_weekly_rows(_stats_frame(), _games_frame(), season=2025, start_week=1, end_week=1)
        db.store_actual_stats(rows, season=2025, week=1, source="test")
        stored = db.conn.execute(
            """
            SELECT p.name, p.position, a.actual_points, a.points_allowed, a.sacks
            FROM actual_stats a JOIN players p ON p.player_id = a.player_id
            WHERE p.position = 'DST'
            """
        ).fetchall()
        assert len(stored) == 4
        kc = next(r for r in stored if r["name"] == "Kansas City Chiefs")
        assert kc["actual_points"] == 19.0
        assert kc["points_allowed"] == 20
        assert kc["sacks"] == 4.0
    finally:
        db.close()


def test_migration_columns_idempotent(tmp_path):
    """K/DST columns exist on a fresh DB and re-init does not fail."""
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(db_path=str(tmp_path / "mig.db"))
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(actual_stats)")}
    db.close()
    db = FFPyDatabase(db_path=str(tmp_path / "mig.db"))  # re-init: no-op
    try:
        cols2 = {row[1] for row in db.conn.execute("PRAGMA table_info(actual_stats)")}
    finally:
        db.close()
    expected = {
        "fg_made",
        "fg_att",
        "fg_missed",
        "fg_long",
        "fgm_0_19",
        "fgm_20_29",
        "fgm_30_39",
        "fgm_40_49",
        "fgm_50_59",
        "fgm_60p",
        "xp_made",
        "xp_att",
        "sacks",
        "def_interceptions",
        "fumble_recoveries",
        "def_tds",
        "safeties",
        "special_teams_tds",
        "blocked_kicks",
        "points_allowed",
    }
    assert expected <= cols
    assert cols == cols2


def test_kicker_store_round_trip(tmp_path):
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(db_path=str(tmp_path / "k.db"))
    try:
        df = pd.DataFrame(
            [
                {
                    "player": "Example K",
                    "team": "KC",
                    "position": "K",
                    "opponent": "BAL",
                    "actual_points": 9.0,
                    "week": 1,
                    "nfl_id": "00-456",
                    "fg_made": 2,
                    "fg_att": 2,
                    "fg_missed": 0,
                    "fg_long": 45,
                    "fgm_20_29": 1,
                    "fgm_40_49": 1,
                    "xp_made": 2,
                    "xp_att": 2,
                }
            ]
        )
        db.store_actual_stats(df, season=2025, week=1, source="test")
        row = db.conn.execute(
            """
            SELECT p.position, a.fg_made, a.fgm_40_49, a.xp_made, a.actual_points
            FROM actual_stats a JOIN players p ON p.player_id = a.player_id
            WHERE p.name = 'Example K'
            """
        ).fetchone()
        assert row["position"] == "K"
        assert row["fg_made"] == 2
        assert row["fgm_40_49"] == 1
        assert row["xp_made"] == 2
        assert row["actual_points"] == 9.0
    finally:
        db.close()
