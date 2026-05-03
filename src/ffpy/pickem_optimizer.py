"""Hyperparameter search + cross-validation for pick'em strategies.

Layered API:
- `grid_search` / `random_search` → enumerate combos, evaluate each on one window.
- `train_test_split` → tune on a train window, report on a held-out test window.
- `walk_forward` → expanding-window CV (K folds, no lookahead).

Every combo is scored by a metric extracted from `BacktestResult`. The default
is `win_rate` for straight-up pools; `confidence_pct` is the right call for
confidence-points pools. Callers may also supply any
`Callable[[BacktestResult], float]`.

Overfitting detection in `train_test_split` is intentionally simple: a flag
fires when `train_metric - test_metric` exceeds a threshold (default 5pp).
The full leaderboard is kept on the result so callers can do their own
inspection.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple, Type, Union

import pandas as pd

from ffpy.database import FFPyDatabase
from ffpy.pickem_backtest import Backtester, BacktestResult, PickStrategy

Metric = Union[str, Callable[[BacktestResult], float]]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Output of `grid_search` / `random_search`.

    `leaderboard` is a DataFrame (one row per combo) sorted by `metric` desc.
    `best_params` is a dict ready to splat into the strategy constructor.
    """

    metric_name: str
    best_params: Dict[str, Any]
    best_metric: float
    leaderboard: pd.DataFrame


@dataclass
class TrainTestResult:
    """Output of `train_test_split`.

    `suspected_overfit` is True when `train_metric - test_metric` exceeds
    the caller's threshold. The leaderboard from the train search is kept
    so callers can inspect the runner-up combos.
    """

    metric_name: str
    best_params: Dict[str, Any]
    train_metric: float
    test_metric: float
    gap: float
    suspected_overfit: bool
    train_result: BacktestResult
    test_result: BacktestResult
    train_leaderboard: pd.DataFrame


@dataclass
class WalkForwardFold:
    """One fold of an expanding-window walk-forward CV."""

    train_seasons: Tuple[int, ...]
    test_season: int
    best_params: Dict[str, Any]
    train_metric: float
    test_metric: float
    n_test_games: int


@dataclass
class WalkForwardResult:
    """K folds of expanding-window walk-forward CV."""

    metric_name: str
    folds: List[WalkForwardFold]
    avg_train_metric: float
    avg_test_metric: float
    avg_gap: float

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "train_seasons": str(list(f.train_seasons)),
                    "test_season": f.test_season,
                    "best_params": f.best_params,
                    "train_metric": f.train_metric,
                    "test_metric": f.test_metric,
                    "gap": f.train_metric - f.test_metric,
                    "n_test_games": f.n_test_games,
                }
                for f in self.folds
            ]
        )


# ---------------------------------------------------------------------------
# StrategyOptimizer
# ---------------------------------------------------------------------------


def _resolve_metric(metric: Metric) -> Tuple[str, Callable[[BacktestResult], float]]:
    if callable(metric):
        return ("custom", metric)
    if metric == "win_rate":
        return ("win_rate", lambda r: r.win_rate)
    if metric == "confidence_pct":
        return ("confidence_pct", lambda r: r.confidence_pct)
    raise ValueError(f"Unknown metric {metric!r}. Use 'win_rate', 'confidence_pct', or a callable.")


def _cartesian(param_grid: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    """Cartesian product of `{key: [values...]}` → list of {key: value} dicts."""
    if not param_grid:
        return [{}]
    keys = list(param_grid.keys())
    values = [list(param_grid[k]) for k in keys]
    if any(len(v) == 0 for v in values):
        raise ValueError("param_grid contains an empty value list")
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


class StrategyOptimizer:
    """Tune a `PickStrategy` over historical windows.

    Args:
        db: An open `FFPyDatabase`.
        strategy_class: A `PickStrategy` subclass with a `__init__(**params)`
            signature compatible with the keys in `param_grid`.
        metric: 'win_rate', 'confidence_pct', or a `BacktestResult → float` fn.
            Higher is better.
        season_type: 'REG' / 'POST' / 'PRE'.
    """

    def __init__(
        self,
        db: FFPyDatabase,
        strategy_class: Type[PickStrategy],
        metric: Metric = "win_rate",
        season_type: str = "REG",
    ):
        self.db = db
        self.strategy_class = strategy_class
        self.metric_name, self._metric_fn = _resolve_metric(metric)
        self.season_type = season_type
        self._bt = Backtester(db)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def grid_search(
        self,
        param_grid: Dict[str, Sequence[Any]],
        season_start: int,
        season_end: int,
        week_start: int = 1,
        week_end: int = 18,
        require_full_coverage: bool = True,
    ) -> SearchResult:
        """Enumerate the full cartesian product of `param_grid` and rank."""
        combos = _cartesian(param_grid)
        return self._evaluate_combos(
            combos, season_start, season_end, week_start, week_end, require_full_coverage
        )

    def random_search(
        self,
        param_dist: Dict[str, Sequence[Any]],
        n_iter: int,
        season_start: int,
        season_end: int,
        week_start: int = 1,
        week_end: int = 18,
        seed: int = 42,
        require_full_coverage: bool = True,
    ) -> SearchResult:
        """Sample `n_iter` combos uniformly (without replacement) from `param_dist`.

        Each value list is treated as a discrete distribution; floats can be
        passed as `np.linspace(...)` lists.
        """
        if n_iter <= 0:
            raise ValueError("n_iter must be > 0")
        if not param_dist:
            raise ValueError("param_dist must contain at least one parameter")
        rng = random.Random(seed)
        seen: set = set()
        combos: List[Dict[str, Any]] = []
        # Cap attempts so a small grid doesn't infinite-loop searching for
        # uniqueness; once the grid is exhausted we just return what we have.
        max_attempts = max(n_iter * 10, 100)
        attempts = 0
        while len(combos) < n_iter and attempts < max_attempts:
            attempts += 1
            combo = {k: rng.choice(list(v)) for k, v in param_dist.items()}
            key = tuple(sorted(combo.items()))
            if key in seen:
                continue
            seen.add(key)
            combos.append(combo)
        return self._evaluate_combos(
            combos, season_start, season_end, week_start, week_end, require_full_coverage
        )

    # ------------------------------------------------------------------
    # Train / test split
    # ------------------------------------------------------------------

    def train_test_split(
        self,
        param_grid: Dict[str, Sequence[Any]],
        train_seasons: Tuple[int, int],
        test_seasons: Tuple[int, int],
        overfit_threshold: float = 0.05,
        require_full_coverage: bool = True,
    ) -> TrainTestResult:
        """Grid-search `param_grid` on the train window, evaluate on test.

        Both windows are inclusive (`(start, end)`). They may overlap if the
        caller insists, but doing so contaminates the test set and silently
        biases the gap metric — caller's responsibility.
        """
        train_search = self.grid_search(
            param_grid,
            season_start=train_seasons[0],
            season_end=train_seasons[1],
            require_full_coverage=require_full_coverage,
        )

        best_params = train_search.best_params
        train_result = self._bt.run(
            self.strategy_class(**best_params),
            season_start=train_seasons[0],
            season_end=train_seasons[1],
            season_type=self.season_type,
            require_full_coverage=require_full_coverage,
        )
        test_result = self._bt.run(
            self.strategy_class(**best_params),
            season_start=test_seasons[0],
            season_end=test_seasons[1],
            season_type=self.season_type,
            require_full_coverage=require_full_coverage,
        )

        train_metric = self._metric_fn(train_result)
        test_metric = self._metric_fn(test_result)
        gap = train_metric - test_metric

        return TrainTestResult(
            metric_name=self.metric_name,
            best_params=best_params,
            train_metric=train_metric,
            test_metric=test_metric,
            gap=gap,
            suspected_overfit=gap > overfit_threshold,
            train_result=train_result,
            test_result=test_result,
            train_leaderboard=train_search.leaderboard,
        )

    # ------------------------------------------------------------------
    # Walk-forward CV
    # ------------------------------------------------------------------

    def walk_forward(
        self,
        param_grid: Dict[str, Sequence[Any]],
        seasons: Sequence[int],
        min_train_seasons: int = 1,
        require_full_coverage: bool = True,
    ) -> WalkForwardResult:
        """Expanding-window walk-forward CV.

        For `seasons=[2021, 2022, 2023]` and `min_train_seasons=1`:
          fold 1: train on [2021]       , test on 2022
          fold 2: train on [2021, 2022] , test on 2023

        No fold ever sees a future season — guards against lookahead bias.
        """
        seasons = sorted(set(seasons))
        if len(seasons) < min_train_seasons + 1:
            raise ValueError(f"walk_forward needs ≥ {min_train_seasons + 1} seasons, got {len(seasons)}")

        folds: List[WalkForwardFold] = []
        for i in range(min_train_seasons, len(seasons)):
            train = tuple(seasons[:i])
            test_season = seasons[i]
            train_search = self.grid_search(
                param_grid,
                season_start=train[0],
                season_end=train[-1],
                require_full_coverage=require_full_coverage,
            )
            test_result = self._bt.run(
                self.strategy_class(**train_search.best_params),
                season_start=test_season,
                season_end=test_season,
                season_type=self.season_type,
                require_full_coverage=require_full_coverage,
            )
            test_metric = self._metric_fn(test_result)
            folds.append(
                WalkForwardFold(
                    train_seasons=train,
                    test_season=test_season,
                    best_params=train_search.best_params,
                    train_metric=train_search.best_metric,
                    test_metric=test_metric,
                    n_test_games=test_result.total_games,
                )
            )

        avg_train = sum(f.train_metric for f in folds) / len(folds)
        avg_test = sum(f.test_metric for f in folds) / len(folds)
        return WalkForwardResult(
            metric_name=self.metric_name,
            folds=folds,
            avg_train_metric=avg_train,
            avg_test_metric=avg_test,
            avg_gap=avg_train - avg_test,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _evaluate_combos(
        self,
        combos: List[Dict[str, Any]],
        season_start: int,
        season_end: int,
        week_start: int,
        week_end: int,
        require_full_coverage: bool,
    ) -> SearchResult:
        if not combos:
            raise ValueError("No combos to evaluate (param grid produced 0 rows)")

        rows: List[Dict[str, Any]] = []
        for combo in combos:
            strategy = self.strategy_class(**combo)
            result = self._bt.run(
                strategy,
                season_start=season_start,
                season_end=season_end,
                week_start=week_start,
                week_end=week_end,
                season_type=self.season_type,
                require_full_coverage=require_full_coverage,
            )
            row = {
                **combo,
                "n_games": result.total_games,
                "correct": result.correct,
                "incorrect": result.incorrect,
                "ties": result.ties,
                "win_rate": round(result.win_rate, 4),
                "confidence_pct": round(result.confidence_pct, 4),
                self.metric_name: round(self._metric_fn(result), 4),
            }
            rows.append(row)

        leaderboard = (
            pd.DataFrame(rows)
            .sort_values(self.metric_name, ascending=False, kind="stable")
            .reset_index(drop=True)
        )
        best_row = leaderboard.iloc[0].to_dict()
        # best_params: just the keys that came from the original combos (drop metrics)
        param_keys = list(combos[0].keys())
        best_params = {k: best_row[k] for k in param_keys}
        return SearchResult(
            metric_name=self.metric_name,
            best_params=best_params,
            best_metric=float(best_row[self.metric_name]),
            leaderboard=leaderboard,
        )
