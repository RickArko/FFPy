"""Phase 4 tests: StrategyOptimizer (grid/random search, train/test, walk-forward).

The tests build small synthetic fixtures designed so different `HomeBoost`
thresholds produce *different* hit rates — that's what lets the optimizer's
ranking and overfitting detection be validated deterministically.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

from ffpy.database import FFPyDatabase
from ffpy.pickem_backtest import (
    BacktestResult,
    HomeBoost,
    WinProbBlend,
)
from ffpy.pickem_optimizer import (
    StrategyOptimizer,
    _cartesian,
    _resolve_metric,
)

# ---------------------------------------------------------------------------
# Fixtures: multi-season DBs with controlled outcomes per season
# ---------------------------------------------------------------------------


def _seed_season(
    cur, season: int, rows: List[Tuple[str, str, str, int, int, float]]
) -> None:
    """rows: list of (game_id_suffix, home, away, home_score, away_score, spread)."""
    for suffix, home, away, hs, as_, sp in rows:
        cur.execute(
            """INSERT INTO games (game_id, season, season_type, week, game_date,
                                  home_team, away_team, home_score, away_score,
                                  spread_line, total_line, game_finished)
               VALUES (?, ?, 'REG', 1, ?, ?, ?, ?, ?, ?, 45.0, 1)""",
            (
                f"{season}_01_{suffix}",
                season,
                f"{season}-09-11",
                home,
                away,
                hs,
                as_,
                sp,
            ),
        )


@pytest.fixture
def fresh_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "opt.db"))
    yield db
    db.close()


@pytest.fixture
def db_multi_season(fresh_db: FFPyDatabase) -> FFPyDatabase:
    """Three seasons of 4 games each, designed so HomeBoost thresholds rank
    *differently* each season — perfect for exposing overfitting:

    2021:  HomeBoost(threshold=3.0) is the unique best (4/4)
    2022:  HomeBoost(threshold=1.0) is the unique best (4/4)
    2023:  Same as 2021 — HomeBoost(threshold=3.0) is the unique best

    Spread convention: positive = home favored (nflverse).
    """
    fresh_db.run_migration("002_play_by_play_schema.sql")
    cur = fresh_db.conn.cursor()

    # 2021 — A is a small upset (home wins despite -2 spread). Threshold 3
    # picks home (right); threshold 1 picks away (wrong).
    _seed_season(
        cur,
        2021,
        [
            ("A", "HA1", "AA1", 17, 14, -2.0),  # away "fav" by 2 → home wins (upset)
            ("B", "HB1", "AB1", 28, 14, 5.0),   # home fav, home wins
            ("C", "HC1", "AC1", 14, 24, -4.0),  # away fav by 4, away wins
            ("D", "HD1", "AD1", 35, 17, 10.0),  # home fav big, home wins
        ],
    )

    # 2022 — A is a no-upset (home loses with -2 spread). Threshold 1 picks
    # away (right); threshold 3 picks home (wrong).
    _seed_season(
        cur,
        2022,
        [
            ("A", "HA2", "AA2", 14, 17, -2.0),  # away fav by 2, away wins
            ("B", "HB2", "AB2", 28, 14, 5.0),   # home fav, home wins
            ("C", "HC2", "AC2", 14, 24, -4.0),  # away fav by 4, away wins
            ("D", "HD2", "AD2", 35, 17, 10.0),  # home fav big, home wins
        ],
    )

    # 2023 — same outcomes as 2021 (threshold 3 wins again)
    _seed_season(
        cur,
        2023,
        [
            ("A", "HA3", "AA3", 17, 14, -2.0),
            ("B", "HB3", "AB3", 28, 14, 5.0),
            ("C", "HC3", "AC3", 14, 24, -4.0),
            ("D", "HD3", "AD3", 35, 17, 10.0),
        ],
    )

    fresh_db.conn.commit()
    return fresh_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestResolveMetric:
    def test_win_rate_string(self):
        name, fn = _resolve_metric("win_rate")
        assert name == "win_rate"
        r = BacktestResult("S", {}, 2022, 2022, 1, 18, "REG", weekly_results=[])
        # A fresh result has 0 decided games → win_rate is 0.0
        assert fn(r) == 0.0

    def test_confidence_pct_string(self):
        name, _ = _resolve_metric("confidence_pct")
        assert name == "confidence_pct"

    def test_callable_metric(self):
        name, fn = _resolve_metric(lambda r: 0.99)
        assert name == "custom"
        assert fn(None) == 0.99  # type: ignore[arg-type]

    def test_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            _resolve_metric("bogus")


class TestCartesian:
    def test_empty_grid(self):
        assert _cartesian({}) == [{}]

    def test_single_param(self):
        assert _cartesian({"x": [1, 2, 3]}) == [{"x": 1}, {"x": 2}, {"x": 3}]

    def test_two_params(self):
        out = _cartesian({"x": [1, 2], "y": ["a", "b"]})
        assert len(out) == 4
        assert {"x": 1, "y": "a"} in out
        assert {"x": 2, "y": "b"} in out

    def test_empty_value_list_raises(self):
        with pytest.raises(ValueError, match="empty value list"):
            _cartesian({"x": []})


# ---------------------------------------------------------------------------
# StrategyOptimizer.grid_search
# ---------------------------------------------------------------------------


class TestGridSearch:
    def test_ranks_by_win_rate(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost, metric="win_rate")
        r = opt.grid_search(
            {"threshold": [1.0, 3.0, 6.0]},
            season_start=2021,
            season_end=2021,
        )
        # Designed: threshold=3.0 → 4/4, threshold=1.0 → 3/4, threshold=6.0 → 3/4
        assert r.best_params == {"threshold": 3.0}
        assert r.best_metric == pytest.approx(1.0, abs=1e-6)
        # Leaderboard sorted desc
        assert r.leaderboard["win_rate"].is_monotonic_decreasing
        # All 3 combos appear
        assert set(r.leaderboard["threshold"]) == {1.0, 3.0, 6.0}

    def test_leaderboard_has_metric_columns(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.grid_search(
            {"threshold": [1.0, 3.0]},
            season_start=2021,
            season_end=2021,
        )
        for col in ("threshold", "n_games", "correct", "win_rate", "confidence_pct"):
            assert col in r.leaderboard.columns

    def test_metric_drives_ranking(self, db_multi_season):
        """Switching metric must change which combo wins (when it differs)."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost, metric="confidence_pct")
        r = opt.grid_search(
            {"threshold": [1.0, 3.0, 6.0]},
            season_start=2021,
            season_end=2021,
        )
        # confidence_pct is the metric — leaderboard sorted by that
        assert r.metric_name == "confidence_pct"
        assert r.leaderboard["confidence_pct"].is_monotonic_decreasing

    def test_two_param_grid(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, WinProbBlend)
        r = opt.grid_search(
            {"home_advantage": [0.0, 2.0], "std": [13.5, 14.0]},
            season_start=2021,
            season_end=2021,
        )
        assert len(r.leaderboard) == 4
        assert set(r.leaderboard["home_advantage"]) == {0.0, 2.0}

    def test_custom_metric(self, db_multi_season):
        """A user-supplied metric callable should be ranked correctly."""
        # Negative win_rate → optimizer should pick the WORST strategy
        opt = StrategyOptimizer(
            db_multi_season, HomeBoost, metric=lambda r: -r.win_rate
        )
        r = opt.grid_search(
            {"threshold": [1.0, 3.0, 6.0]},
            season_start=2021,
            season_end=2021,
        )
        # threshold=3.0 is the BEST under win_rate, so it's the worst here
        # The chosen "best" should NOT be 3.0
        assert r.best_params["threshold"] != 3.0


# ---------------------------------------------------------------------------
# StrategyOptimizer.random_search
# ---------------------------------------------------------------------------


class TestRandomSearch:
    def test_deterministic_with_seed(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r1 = opt.random_search(
            {"threshold": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]},
            n_iter=4,
            season_start=2021, season_end=2021,
            seed=7,
        )
        r2 = opt.random_search(
            {"threshold": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]},
            n_iter=4,
            season_start=2021, season_end=2021,
            seed=7,
        )
        assert r1.best_params == r2.best_params
        # Same combos should have been sampled
        assert set(r1.leaderboard["threshold"]) == set(r2.leaderboard["threshold"])

    def test_dedupe_caps_at_grid_size(self, db_multi_season):
        """If the grid has only 3 unique combos, n_iter=10 returns at most 3 rows."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.random_search(
            {"threshold": [1.0, 3.0, 6.0]},
            n_iter=10,
            season_start=2021, season_end=2021,
        )
        assert len(r.leaderboard) <= 3

    def test_zero_n_iter_raises(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        with pytest.raises(ValueError, match="n_iter"):
            opt.random_search(
                {"threshold": [1.0]}, n_iter=0,
                season_start=2021, season_end=2021,
            )

    def test_empty_dist_raises(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        with pytest.raises(ValueError, match="param_dist"):
            opt.random_search(
                {}, n_iter=5,
                season_start=2021, season_end=2021,
            )


# ---------------------------------------------------------------------------
# StrategyOptimizer.train_test_split
# ---------------------------------------------------------------------------


class TestTrainTestSplit:
    def test_picks_best_on_train_evaluates_on_test(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.train_test_split(
            {"threshold": [1.0, 3.0, 6.0]},
            train_seasons=(2021, 2021),
            test_seasons=(2022, 2022),
        )
        # Train winner is threshold=3.0 (4/4 on 2021)
        assert r.best_params == {"threshold": 3.0}
        assert r.train_metric == pytest.approx(1.0, abs=1e-6)
        # On 2022 with threshold=3.0: A wrong, B right, C right, D right → 3/4
        assert r.test_metric == pytest.approx(0.75, abs=1e-6)

    def test_overfit_flag_fires(self, db_multi_season):
        """gap = 1.0 - 0.75 = 0.25 > 0.05 → flagged."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.train_test_split(
            {"threshold": [1.0, 3.0, 6.0]},
            train_seasons=(2021, 2021),
            test_seasons=(2022, 2022),
            overfit_threshold=0.05,
        )
        assert r.suspected_overfit is True
        assert r.gap == pytest.approx(0.25, abs=1e-6)

    def test_overfit_flag_silent_with_high_threshold(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.train_test_split(
            {"threshold": [1.0, 3.0, 6.0]},
            train_seasons=(2021, 2021),
            test_seasons=(2022, 2022),
            overfit_threshold=0.50,
        )
        assert r.suspected_overfit is False

    def test_holds_full_train_leaderboard(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.train_test_split(
            {"threshold": [1.0, 3.0, 6.0]},
            train_seasons=(2021, 2021),
            test_seasons=(2022, 2022),
        )
        assert len(r.train_leaderboard) == 3

    def test_results_are_actual_backtest_results(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.train_test_split(
            {"threshold": [1.0, 3.0]},
            train_seasons=(2021, 2021),
            test_seasons=(2022, 2022),
        )
        assert isinstance(r.train_result, BacktestResult)
        assert isinstance(r.test_result, BacktestResult)
        assert r.train_result.season_start == 2021
        assert r.test_result.season_start == 2022


# ---------------------------------------------------------------------------
# StrategyOptimizer.walk_forward
# ---------------------------------------------------------------------------


class TestWalkForward:
    def test_n_folds_equals_seasons_minus_min_train(self, db_multi_season):
        """With 3 seasons and min_train_seasons=1 → 2 folds."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.walk_forward(
            {"threshold": [1.0, 3.0, 6.0]},
            seasons=[2021, 2022, 2023],
        )
        assert len(r.folds) == 2

    def test_no_lookahead(self, db_multi_season):
        """Each fold's train_seasons must be strictly before its test_season."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.walk_forward(
            {"threshold": [1.0, 3.0]},
            seasons=[2021, 2022, 2023],
        )
        for fold in r.folds:
            assert max(fold.train_seasons) < fold.test_season

    def test_expanding_window(self, db_multi_season):
        """Fold 1 trains on [2021], fold 2 trains on [2021, 2022]."""
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.walk_forward(
            {"threshold": [1.0, 3.0]},
            seasons=[2021, 2022, 2023],
        )
        assert r.folds[0].train_seasons == (2021,)
        assert r.folds[0].test_season == 2022
        assert r.folds[1].train_seasons == (2021, 2022)
        assert r.folds[1].test_season == 2023

    def test_too_few_seasons_raises(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        with pytest.raises(ValueError, match=r"≥ 2 seasons"):
            opt.walk_forward(
                {"threshold": [1.0]}, seasons=[2021], min_train_seasons=1,
            )

    def test_to_frame_returns_dataframe(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.walk_forward(
            {"threshold": [1.0, 3.0]},
            seasons=[2021, 2022, 2023],
        )
        df = r.to_frame()
        assert len(df) == 2
        for col in ("train_seasons", "test_season", "best_params",
                    "train_metric", "test_metric", "gap", "n_test_games"):
            assert col in df.columns

    def test_avg_metrics_match_fold_means(self, db_multi_season):
        opt = StrategyOptimizer(db_multi_season, HomeBoost)
        r = opt.walk_forward(
            {"threshold": [1.0, 3.0, 6.0]},
            seasons=[2021, 2022, 2023],
        )
        avg_test_manual = sum(f.test_metric for f in r.folds) / len(r.folds)
        assert r.avg_test_metric == pytest.approx(avg_test_manual)


# ---------------------------------------------------------------------------
# Integration / acceptance: real DB if present
# ---------------------------------------------------------------------------


REAL_DB_PATH = Path.home() / ".ffpy" / "ffpy.db"


@pytest.mark.skipif(
    not REAL_DB_PATH.exists(),
    reason=f"Real local DB not present at {REAL_DB_PATH}",
)
class TestOptimizerRealDB:
    def test_homeboost_train_test_2021_to_2022(self):
        """Tune HomeBoost on 2021, evaluate on 2022. Just sanity-checks the
        plumbing — exact numbers depend on the data window."""
        with FFPyDatabase(db_path=str(REAL_DB_PATH)) as db:
            opt = StrategyOptimizer(db, HomeBoost, metric="win_rate")
            r = opt.train_test_split(
                {"threshold": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]},
                train_seasons=(2021, 2021),
                test_seasons=(2022, 2022),
            )
        assert "threshold" in r.best_params
        assert 0.5 <= r.train_metric <= 0.8
        assert 0.5 <= r.test_metric <= 0.8
        # Print so verbose runs show the user what tuning chose
        print(
            f"\n  HomeBoost tuned on 2021: threshold={r.best_params['threshold']} "
            f"(train={r.train_metric:.1%}, test={r.test_metric:.1%}, gap={r.gap:+.1%}, "
            f"overfit={r.suspected_overfit})"
        )
