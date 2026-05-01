"""Historical pick'em strategy backtester.

A `PickStrategy` produces one `Pick` per game in a (season, week) slate using
ONLY pre-game information. The `Backtester` runs a strategy across a multi-
season window, grades picks against actual outcomes, and optionally persists
results to `backtest_runs` / `backtest_picks`.

Spread convention (nflverse / nflfastR): `spread_line` is the home team's
expected margin. `spread_line > 0` means the HOME team is favored, `< 0`
means the AWAY team is favored, `0` is a pick'em.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from ffpy.database import FFPyDatabase

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pick:
    """One pick output by a strategy. `confidence=None` for straight-up pools."""

    game_id: str
    selected_team: str
    confidence: Optional[int] = None


@dataclass(frozen=True)
class GradedPick:
    """A `Pick` plus its outcome. `correct=None` represents a tie."""

    pick: Pick
    correct: Optional[int]  # 1 = right, 0 = wrong, None = tie / ungraded


@dataclass
class WeekResult:
    """Aggregates for one (season, week). Counts derive from `graded_picks`."""

    season: int
    week: int
    n_games: int
    graded_picks: List[GradedPick]

    @property
    def correct(self) -> int:
        return sum(1 for gp in self.graded_picks if gp.correct == 1)

    @property
    def incorrect(self) -> int:
        return sum(1 for gp in self.graded_picks if gp.correct == 0)

    @property
    def ties(self) -> int:
        return sum(1 for gp in self.graded_picks if gp.correct is None)

    @property
    def confidence_earned(self) -> int:
        return sum(
            (gp.pick.confidence or 0) for gp in self.graded_picks if gp.correct == 1
        )

    @property
    def confidence_max(self) -> int:
        return sum((gp.pick.confidence or 0) for gp in self.graded_picks)


@dataclass
class BacktestResult:
    """Final aggregate of a backtest run. Persisted via `Backtester._persist`."""

    strategy_name: str
    strategy_params: Dict[str, Any]
    season_start: int
    season_end: int
    week_start: int
    week_end: int
    season_type: str
    weekly_results: List[WeekResult] = field(default_factory=list)
    run_id: Optional[int] = None  # set after persist()

    @property
    def total_games(self) -> int:
        return sum(wr.n_games for wr in self.weekly_results)

    @property
    def correct(self) -> int:
        return sum(wr.correct for wr in self.weekly_results)

    @property
    def incorrect(self) -> int:
        return sum(wr.incorrect for wr in self.weekly_results)

    @property
    def ties(self) -> int:
        return sum(wr.ties for wr in self.weekly_results)

    @property
    def confidence_earned(self) -> int:
        return sum(wr.confidence_earned for wr in self.weekly_results)

    @property
    def confidence_max(self) -> int:
        return sum(wr.confidence_max for wr in self.weekly_results)

    @property
    def win_rate(self) -> float:
        decided = self.correct + self.incorrect
        return self.correct / decided if decided > 0 else 0.0

    @property
    def confidence_pct(self) -> float:
        return (
            self.confidence_earned / self.confidence_max
            if self.confidence_max > 0
            else 0.0
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "params": self.strategy_params,
            "season_start": self.season_start,
            "season_end": self.season_end,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "season_type": self.season_type,
            "n_games": self.total_games,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "ties": self.ties,
            "win_rate": round(self.win_rate, 4),
            "confidence_earned": self.confidence_earned,
            "confidence_max": self.confidence_max,
            "confidence_pct": round(self.confidence_pct, 4),
        }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _favorite_team(spread_line: float, home_team: str, away_team: str) -> str:
    """Return the favored team. `spread_line >= 0` picks home (pickem defaults home).

    nflverse convention: `spread_line` is the home team's expected margin, so
    positive ⇒ home favored, negative ⇒ away favored.
    """
    return home_team if spread_line >= 0 else away_team


def spread_to_wp(spread_line: float, std: float = 13.5) -> float:
    """Map an expected home margin to home win-probability via normal CDF.

    Models the final margin as Normal(spread_line, std²) and returns
    P(margin > 0). NFL historical std of margin is ~13.5 points.

    Args:
        spread_line: Expected home margin (nflverse convention; positive ⇒
            home favored).
        std: Standard deviation of the margin distribution.

    Returns:
        P(home wins) ∈ [0, 1].
    """
    if std <= 0:
        raise ValueError(f"std must be > 0, got {std}")
    z = spread_line / (std * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


class PickStrategy(ABC):
    """Strategy interface: takes a one-week games DataFrame, returns Picks.

    Subclasses MUST NOT inspect any column derived from outcomes (`home_score`,
    `away_score`); only pre-game info such as `spread_line`, `total_line`,
    teams, and venue.
    """

    name: str = "BaseStrategy"

    def __init__(self, **params: Any):
        self.params: Dict[str, Any] = params

    @abstractmethod
    def pick(self, games_df: pd.DataFrame) -> List[Pick]: ...


class AllFavorites(PickStrategy):
    """Always pick the spread favorite. Skip games with NULL spread.

    Straight-up pool: `confidence` is left None.
    """

    name = "AllFavorites"

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        picks: List[Pick] = []
        for _, row in games_df.iterrows():
            if pd.isna(row["spread_line"]):
                continue
            team = _favorite_team(
                float(row["spread_line"]), row["home_team"], row["away_team"]
            )
            picks.append(Pick(game_id=row["game_id"], selected_team=team))
        return picks


class ConfidenceBySpread(PickStrategy):
    """Pick the favorite, weight confidence by `|spread|`.

    For n games picked: largest `|spread|` gets confidence n, next n-1, ...,
    smallest 1. Standard NFL confidence-pool format. Tiebreak by `game_id`
    for determinism.
    """

    name = "ConfidenceBySpread"

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        df = games_df.dropna(subset=["spread_line"]).copy()
        if df.empty:
            return []
        df["abs_spread"] = df["spread_line"].abs()
        df = df.sort_values(
            ["abs_spread", "game_id"], ascending=[False, True]
        ).reset_index(drop=True)
        n = len(df)
        picks: List[Pick] = []
        for i, row in df.iterrows():
            team = _favorite_team(
                float(row["spread_line"]), row["home_team"], row["away_team"]
            )
            picks.append(
                Pick(
                    game_id=row["game_id"],
                    selected_team=team,
                    confidence=n - int(i),
                )
            )
        return picks


def _confidence_by_abs_spread(df: pd.DataFrame) -> pd.DataFrame:
    """Sort `df` so the largest-|spread| game is first; tiebreak by `game_id`.

    Used by every confidence-style strategy so confidence assignment stays
    consistent across the library.
    """
    out = df.copy()
    out["abs_spread"] = out["spread_line"].abs()
    return out.sort_values(
        ["abs_spread", "game_id"], ascending=[False, True]
    ).reset_index(drop=True)


class WinProbBlend(PickStrategy):
    """Pick by win-probability after a home-field bump.

    Adjusted home margin = `spread_line + home_advantage`, mapped via normal
    CDF to home WP. Picks home when WP ≥ 0.5, else away. Confidence ranked
    by `|WP − 0.5|` descending — the most lopsided games get the highest
    confidence points.
    """

    name = "WinProbBlend"

    def __init__(self, home_advantage: float = 2.0, std: float = 13.5):
        super().__init__(home_advantage=home_advantage, std=std)
        self.home_advantage = float(home_advantage)
        self.std = float(std)

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        df = games_df.dropna(subset=["spread_line"]).copy()
        if df.empty:
            return []
        df["adj_spread"] = df["spread_line"] + self.home_advantage
        df["home_wp"] = df["adj_spread"].apply(
            lambda s: spread_to_wp(float(s), self.std)
        )
        df["edge"] = (df["home_wp"] - 0.5).abs()
        df = df.sort_values(
            ["edge", "game_id"], ascending=[False, True]
        ).reset_index(drop=True)
        n = len(df)
        picks: List[Pick] = []
        for i, row in df.iterrows():
            team = row["home_team"] if row["home_wp"] >= 0.5 else row["away_team"]
            picks.append(
                Pick(game_id=row["game_id"], selected_team=team, confidence=n - int(i))
            )
        return picks


class HomeBoost(PickStrategy):
    """Default to favorite, but flip to home team for `|spread| ≤ threshold`.

    Bets that home-field advantage is mispriced in toss-up games.
    Confidence ranked by `|spread|`.
    """

    name = "HomeBoost"

    def __init__(self, threshold: float = 3.0):
        super().__init__(threshold=threshold)
        self.threshold = float(threshold)

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        df = games_df.dropna(subset=["spread_line"])
        if df.empty:
            return []
        df = _confidence_by_abs_spread(df)
        n = len(df)
        picks: List[Pick] = []
        for i, row in df.iterrows():
            spread = float(row["spread_line"])
            if abs(spread) <= self.threshold:
                team = row["home_team"]
            else:
                team = _favorite_team(spread, row["home_team"], row["away_team"])
            picks.append(
                Pick(game_id=row["game_id"], selected_team=team, confidence=n - int(i))
            )
        return picks


class UnderdogTargeted(PickStrategy):
    """Default to favorite, but switch to underdog for `0 < |spread| ≤ threshold`.

    Inverse of `HomeBoost`. Pick'ems (spread = 0) keep the home default to
    avoid an arbitrary coin-flip choice.
    """

    name = "UnderdogTargeted"

    def __init__(self, threshold: float = 3.0):
        super().__init__(threshold=threshold)
        self.threshold = float(threshold)

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        df = games_df.dropna(subset=["spread_line"])
        if df.empty:
            return []
        df = _confidence_by_abs_spread(df)
        n = len(df)
        picks: List[Pick] = []
        for i, row in df.iterrows():
            spread = float(row["spread_line"])
            home, away = row["home_team"], row["away_team"]
            fav = _favorite_team(spread, home, away)
            if 0 < abs(spread) <= self.threshold:
                team = away if fav == home else home  # the dog
            else:
                team = fav
            picks.append(
                Pick(game_id=row["game_id"], selected_team=team, confidence=n - int(i))
            )
        return picks


class Consensus(PickStrategy):
    """Majority vote across N inner strategies; tie-break by `_favorite_team`.

    Each inner strategy contributes one vote per game. The team with the most
    votes wins the slate; on a vote tie, the spread favorite wins. Confidence
    is ranked by `|spread|` (decoupled from the voting margin so the API
    stays consistent with the rest of the library).
    """

    name = "Consensus"

    def __init__(self, strategies: Sequence[PickStrategy]):
        if len(strategies) == 0:
            raise ValueError("Consensus requires at least one inner strategy")
        super().__init__(
            strategies=[
                {"name": s.name, "params": dict(s.params)} for s in strategies
            ]
        )
        self.strategies: List[PickStrategy] = list(strategies)

    def pick(self, games_df: pd.DataFrame) -> List[Pick]:
        df = games_df.dropna(subset=["spread_line"])
        if df.empty:
            return []

        votes_by_game: Dict[str, Counter] = {}
        for s in self.strategies:
            for pk in s.pick(games_df):
                votes_by_game.setdefault(pk.game_id, Counter())[pk.selected_team] += 1

        df = _confidence_by_abs_spread(df)
        n = len(df)
        picks: List[Pick] = []
        for i, row in df.iterrows():
            gid = row["game_id"]
            votes = votes_by_game.get(gid)
            if not votes:
                continue
            ranked = votes.most_common()
            if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
                team = _favorite_team(
                    float(row["spread_line"]), row["home_team"], row["away_team"]
                )
            else:
                team = ranked[0][0]
            picks.append(
                Pick(game_id=gid, selected_team=team, confidence=n - int(i))
            )
        return picks


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------


def _grade(pick: Pick, row: pd.Series) -> Optional[int]:
    """Return 1 if pick correct, 0 if wrong, None if tie."""
    if row["home_score"] == row["away_score"]:
        return None
    winner = (
        row["home_team"] if row["home_score"] > row["away_score"] else row["away_team"]
    )
    return 1 if pick.selected_team == winner else 0


class Backtester:
    """Run pick'em strategies over historical (season, week) windows."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def run(
        self,
        strategy: PickStrategy,
        season_start: int,
        season_end: int,
        week_start: int = 1,
        week_end: int = 18,
        season_type: str = "REG",
        require_full_coverage: bool = True,
        persist: bool = False,
        note: Optional[str] = None,
    ) -> BacktestResult:
        """Execute `strategy` across the given window and grade every pick.

        Args:
            strategy: Concrete `PickStrategy` instance.
            season_start: Inclusive lower season bound.
            season_end:   Inclusive upper season bound.
            week_start:   Inclusive starting week (default 1).
            week_end:     Inclusive ending week (default 18).
            season_type:  'REG' / 'POST' / 'PRE'.
            require_full_coverage: If True, raises when any (season, week) in
                the window is missing spreads or scores. Pass False to silently
                skip incomplete weeks (the strategy itself can still skip games
                it can't grade — e.g. NULL spread).
            persist: If True, write aggregates + per-pick rows to the
                `backtest_runs` / `backtest_picks` tables.
            note: Optional free-text note attached to the persisted run.
        """
        if require_full_coverage:
            self._verify_coverage(season_start, season_end, week_start, week_end, season_type)

        weekly: List[WeekResult] = []
        for season in range(season_start, season_end + 1):
            games = self.db.get_historical_games(
                season=season, season_type=season_type, finished_only=True
            )
            if games.empty:
                continue
            games = games[
                (games["week"] >= week_start) & (games["week"] <= week_end)
            ]
            if games.empty:
                continue

            for week, week_df in games.groupby("week", sort=True):
                weekly.append(
                    self._run_week(strategy, int(season), int(week), week_df)
                )

        result = BacktestResult(
            strategy_name=strategy.name,
            strategy_params=strategy.params,
            season_start=season_start,
            season_end=season_end,
            week_start=week_start,
            week_end=week_end,
            season_type=season_type,
            weekly_results=weekly,
        )

        if persist:
            result.run_id = self._persist(result, note=note)

        return result

    def compare(
        self,
        strategies: Sequence[PickStrategy],
        season_start: int,
        season_end: int,
        week_start: int = 1,
        week_end: int = 18,
        season_type: str = "REG",
        require_full_coverage: bool = True,
        persist: bool = False,
    ) -> pd.DataFrame:
        """Run several strategies on the same window; return ranked summary."""
        rows: List[Dict[str, Any]] = []
        for s in strategies:
            r = self.run(
                s,
                season_start=season_start,
                season_end=season_end,
                week_start=week_start,
                week_end=week_end,
                season_type=season_type,
                require_full_coverage=require_full_coverage,
                persist=persist,
            )
            rows.append(r.to_summary_dict())
        return (
            pd.DataFrame(rows)
            .sort_values(["win_rate", "confidence_pct"], ascending=[False, False])
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _verify_coverage(
        self,
        season_start: int,
        season_end: int,
        week_start: int,
        week_end: int,
        season_type: str,
    ) -> None:
        cov = self.db.get_data_coverage(
            season_start=season_start, season_end=season_end, season_type=season_type
        )
        if cov.empty:
            raise ValueError(
                f"No {season_type} games in DB for {season_start}-{season_end}. "
                "Load data via scripts/populate_plays.py first."
            )
        cov = cov[(cov["week"] >= week_start) & (cov["week"] <= week_end)]
        unusable = cov[cov["fully_usable"] == 0]
        if not unusable.empty:
            preview = unusable[
                ["season", "week", "n_games", "with_spread", "with_scores"]
            ].to_string(index=False)
            raise ValueError(
                f"{len(unusable)} (season, week) windows are not fully usable.\n"
                f"Pass require_full_coverage=False to skip them.\n{preview}"
            )

    def _run_week(
        self,
        strategy: PickStrategy,
        season: int,
        week: int,
        week_df: pd.DataFrame,
    ) -> WeekResult:
        picks = strategy.pick(week_df)
        idx = week_df.set_index("game_id")
        graded: List[GradedPick] = []
        for pk in picks:
            if pk.game_id not in idx.index:
                continue  # strategy returned a game not in this week's slate
            graded.append(GradedPick(pick=pk, correct=_grade(pk, idx.loc[pk.game_id])))
        return WeekResult(
            season=season, week=week, n_games=len(week_df), graded_picks=graded
        )

    def _persist(self, r: BacktestResult, note: Optional[str] = None) -> int:
        cur = self.db.conn.cursor()
        cur.execute(
            """INSERT INTO backtest_runs (
                strategy_name, strategy_params,
                season_start, season_end, week_start, week_end, season_type,
                total_games, correct, incorrect, ties,
                confidence_earned, confidence_max, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.strategy_name,
                json.dumps(r.strategy_params, default=str, sort_keys=True),
                r.season_start,
                r.season_end,
                r.week_start,
                r.week_end,
                r.season_type,
                r.total_games,
                r.correct,
                r.incorrect,
                r.ties,
                r.confidence_earned,
                r.confidence_max,
                note,
            ),
        )
        run_id = cur.lastrowid

        pick_rows = [
            (
                run_id,
                wr.season,
                wr.week,
                gp.pick.game_id,
                gp.pick.selected_team,
                gp.pick.confidence,
                gp.correct,
            )
            for wr in r.weekly_results
            for gp in wr.graded_picks
        ]
        if pick_rows:
            cur.executemany(
                """INSERT INTO backtest_picks (
                    run_id, season, week, game_id,
                    selected_team, confidence, correct
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                pick_rows,
            )

        self.db.conn.commit()
        return run_id
