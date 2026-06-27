"""
Projection model based on historical player performance.

This module generates fantasy projections by analyzing each player's
recent actual performance and applying statistical models.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase
from ffpy.scoring import ScoringConfig, calculate_points_from_projection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature containers
# ---------------------------------------------------------------------------


@dataclass
class VolumeFeatures:
    """Volume-related features derived from advanced stats and depth charts."""

    target_share: Optional[float] = None
    air_yards_share: Optional[float] = None
    avg_target_distance: Optional[float] = None
    snap_pct: Optional[float] = None
    route_pct: Optional[float] = None
    depth_spot: Optional[int] = None
    targets_per_game: Optional[float] = None
    carries_per_game: Optional[float] = None
    rz_targets_per_game: Optional[float] = None
    ez_targets_per_game: Optional[float] = None


@dataclass
class EfficiencyFeatures:
    """Efficiency features derived from Next Gen Stats."""

    cpoe: Optional[float] = None  # completion % above expectation (QB)
    avg_separation: Optional[float] = None  # separation at target (WR)
    yac_above_expectation: Optional[float] = None  # YAC over expected (WR/TE)
    ryoe_per_att: Optional[float] = None  # rush yards over expected per att (RB)


@dataclass
class InjuryInfo:
    """Player injury status and discount factor."""

    game_status: Optional[str] = None
    discount: float = 1.0
    practice_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Position-base constants
# ---------------------------------------------------------------------------

LEAGUE_AVG_TARGET_SHARE: Dict[str, float] = {
    "WR": 0.16, "TE": 0.12, "RB": 0.08,
}

DEPTH_CHART_PRIORS: Dict[str, Dict[int, float]] = {
    "WR": {1: 0.22, 2: 0.16, 3: 0.10, 4: 0.05},
    "TE": {1: 0.15, 2: 0.10, 3: 0.05},
    "RB": {1: 0.55, 2: 0.35, 3: 0.10},  # snap share priors
}

INJURY_DISCOUNTS: Dict[str, float] = {
    "Out": 0.0,
    "Doubtful": 0.2,
    "Questionable": 0.75,
    "Active": 1.0,
}


def _get_league_avg_target_share(position: str) -> float:
    """Return the league-average target share for a given position."""
    return LEAGUE_AVG_TARGET_SHARE.get(position, 0.10)


def _get_depth_chart_prior(position: str, depth_spot: int) -> Optional[float]:
    """Get the expected target/snap share prior from depth chart position."""
    pos_priors = DEPTH_CHART_PRIORS.get(position, {})
    return pos_priors.get(depth_spot)


def _injury_discount(game_status: Optional[str]) -> float:
    """Map game_status string to a numeric discount factor."""
    if game_status is None:
        return 1.0
    return INJURY_DISCOUNTS.get(game_status, 1.0)


# ==================== Weighted blending helpers ====================


def _blend_prior_with_history(
    history_value: Optional[float],
    prior_value: Optional[float],
    weeks_of_history: int,
    ramp_weeks: int = 4,
) -> Optional[float]:
    """Blend a depth-chart-based prior with historical data.

    Early in the season (few weeks of history) the prior dominates; once
    enough games have been played the history takes over.
    """
    if prior_value is None:
        return history_value
    if history_value is None:
        return prior_value
    alpha = min(weeks_of_history / ramp_weeks, 1.0)
    return history_value * alpha + prior_value * (1.0 - alpha)


# ======================================================================
# EnhancedProjectionModel
# ======================================================================


class EnhancedProjectionModel:
    """Composable projection pipeline that layers feature adjustments on
    top of the weighted-average baseline.

    Pipeline (applied in order):
      1. Baseline projection   (delegates to HistoricalProjectionModel)
      2. Volume adjustment     (target share, snap %, depth chart)
      3. Efficiency adjustment (Next Gen Stats)
      4. TD probability        (red zone / end zone targets)
      5. Injury discount
      6. Defensive matchup     (EPA allowed by opposing defence)
    """

    def __init__(
        self,
        db: Optional[FFPyDatabase] = None,
        scoring: Optional[ScoringConfig] = None,
    ):
        self.db = db if db else FFPyDatabase()
        self.scoring = scoring if scoring else ScoringConfig.ppr()
        self._baseline_model = HistoricalProjectionModel(db=self.db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_projections(
        self,
        season: int,
        week: int,
        lookback_weeks: int = 4,
        recent_weight: float = 0.6,
        disable_features: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Generate enhanced projections for all active players.

        Args:
            season: Target season.
            week: Target week to project.
            lookback_weeks: Number of past weeks for baseline.
            recent_weight: Weight for recent games in baseline.
            disable_features: Optional list of feature names to skip, e.g.
                ``["efficiency", "matchup"]``.

        Returns:
            DataFrame with stat-level projections and ``projected_points``.
        """
        disabled = set(disable_features or [])

        baseline_df = self._baseline_model.generate_projections(
            season=season, week=week,
            lookback_weeks=lookback_weeks, recent_weight=recent_weight,
        )
        if baseline_df.empty:
            return baseline_df

        rows = []
        for _, row in baseline_df.iterrows():
            try:
                enhanced = self._project_player(
                    player_name=row["player"],
                    season=season,
                    target_week=week,
                    baseline_row=row,
                    lookback_weeks=lookback_weeks,
                    disabled=disabled,
                )
                if enhanced:
                    rows.append(enhanced)
            except Exception:
                logger.exception("Failed to enhance projection for %s", row.get("player"))
                rows.append(row.to_dict())

        return pd.DataFrame(rows)

    def _project_player(
        self,
        player_name: str,
        season: int,
        target_week: int,
        baseline_row: pd.Series,
        lookback_weeks: int = 4,
        disabled: Optional[set] = None,
    ) -> Optional[dict]:
        disabled = disabled or set()
        """Run the full enhancement pipeline for a single player."""
        position = baseline_row.get("position", "")
        proj = dict(baseline_row)

        # --- 1. Baseline is already in *proj* ---
        # --- 2. Volume features ---
        if "volume" not in disabled:
            vol = self._get_volume_features(player_name, season, target_week, position)
            vol_adj = self._adjust_volume(proj, vol, position)
            proj.update(vol_adj)

        # --- 3. Efficiency features ---
        if "efficiency" not in disabled:
            eff = self._get_efficiency_features(player_name, season, target_week, position)
            eff_adj = self._adjust_efficiency(proj, eff, position)
            proj.update(eff_adj)

        # --- 4. TD probability ---
        if "td_prob" not in disabled:
            td = self._get_td_probability(player_name, season, target_week, position)
            td_adj = self._adjust_td_projection(proj, td, position)
            proj.update(td_adj)

        # --- 5. Injury ---
        if "injury" not in disabled:
            inj = self._get_injury_adjustment(player_name, season, target_week)
            proj["injury_discount"] = inj.discount
            proj["injury_status"] = inj.game_status or "Active"
        else:
            proj["injury_discount"] = 1.0
            proj["injury_status"] = "Active"

        # --- 6. Defensive matchup ---
        if "matchup" not in disabled:
            mup = self._get_defensive_matchup(player_name, season, target_week, position)
            proj["matchup_factor"] = mup

        # --- Apply injury + matchup discounts ---
        proj = self._apply_final_discounts(proj)

        # --- Recalculate fantasy points from stat projections ---
        proj["projected_points"] = round(
            calculate_points_from_projection(proj, self.scoring), 1
        )

        # Recalculate consistency
        history = self.db.get_player_history(player_name, num_weeks=lookback_weeks)
        if not history.empty:
            proj["consistency"] = round(history["actual_points"].std(), 1)

        return proj

    # ------------------------------------------------------------------
    # Feature extractors
    # ------------------------------------------------------------------

    def _get_volume_features(
        self,
        player_name: str,
        season: int,
        target_week: int,
        position: str,
    ) -> VolumeFeatures:
        """Collect volume-related features for a player."""
        features = VolumeFeatures()

        # Advanced stats (player_advanced_stats)
        adv = self.db.get_player_advanced_stats(player_name, season)
        if not adv.empty:
            recent = adv[adv["week"] < target_week].tail(4)
            if not recent.empty:
                features.target_share = float(recent["target_share"].mean())
                features.air_yards_share = float(recent["air_yards_share"].mean())
                features.avg_target_distance = float(recent["avg_target_distance"].mean())
                features.snap_pct = float(recent["snap_pct"].mean())
                features.route_pct = float(recent["route_pct"].mean())
                features.rz_targets_per_game = float(recent["red_zone_targets"].mean())
                features.ez_targets_per_game = float(recent["end_zone_targets"].mean())

        # Depth chart
        depth = self.db.get_depth_charts(
            season=season, week=target_week, position=position,
        )
        if not depth.empty:
            row = depth[depth["player_name"] == player_name]
            if not row.empty:
                features.depth_spot = int(row.iloc[0]["depth_spot"])

        # Historical per-game volume
        hist = self.db.get_player_history(player_name, num_weeks=8)
        if not hist.empty:
            past = hist[hist["week"] < target_week]
            if not past.empty:
                features.targets_per_game = float(past["receptions"].mean())  # proxied
                features.carries_per_game = float(past["rushing_yards"].mean() / 4.5)

        # --- Blend depth-chart prior for early-season weeks ---
        weeks_of_history = len(adv[adv["week"] < target_week])
        prior = _get_depth_chart_prior(position, features.depth_spot) if features.depth_spot else None
        if prior is not None and features.target_share is not None:
            features.target_share = _blend_prior_with_history(
                features.target_share, prior, weeks_of_history
            )

        # --- Rookie / draft-capital boost (Phase 1: rosters) ---
        try:
            dc = self.db.get_rookie_draft_capital(player_name, season)
            is_rookie = self.db.is_rookie(player_name, season)
        except Exception:
            dc = None
            is_rookie = False

        if is_rookie and weeks_of_history < 3:
            # Rookies with high draft capital get a volume bridge
            if dc and dc["draft_round"] <= 3:
                rookie_mult = 1.0 + (0.15 / dc["draft_round"])  # Round 1: +15%, Round 2: +7.5%, etc.
                if features.target_share is not None:
                    features.target_share = min(features.target_share * rookie_mult,
                                                _get_league_avg_target_share(position) * 1.5)
                if position == "RB" and features.snap_pct is not None:
                    features.snap_pct = min(features.snap_pct * rookie_mult, 0.65)
            # Undrafted rookies get a small floor boost
            elif dc is None or dc["draft_round"] > 6:
                if features.target_share is not None:
                    features.target_share = max(features.target_share,
                                                _get_league_avg_target_share(position) * 0.5)
        elif is_rookie and dc is not None and dc["draft_round"] <= 2:
            # Even with some history, high-pick rookies get a mild boost
            if features.target_share is not None:
                features.target_share = min(features.target_share * 1.08,
                                            _get_league_avg_target_share(position) * 1.3)

        return features

    def _get_efficiency_features(
        self,
        player_name: str,
        season: int,
        target_week: int,
        position: str,
    ) -> EfficiencyFeatures:
        """Collect Next Gen Stats efficiency metrics."""
        features = EfficiencyFeatures()

        ngs = self.db.get_nextgen_stats(player_name=player_name, season=season)
        if ngs.empty:
            return features

        recent = ngs[ngs["week"] < target_week].tail(4)
        if recent.empty:
            return features

        # QB
        if position == "QB":
            features.cpoe = float(recent["completion_percentage_above_expectation"].mean())
        # WR / TE
        elif position in ("WR", "TE"):
            features.avg_separation = float(recent["avg_separation"].mean())
            features.yac_above_expectation = float(recent["avg_yac_above_expectation"].mean())
        # RB
        elif position == "RB":
            features.ryoe_per_att = float(recent["rush_yards_over_expected_per_att"].mean())

        return features

    def _get_injury_adjustment(
        self,
        player_name: str,
        season: int,
        target_week: int,
    ) -> InjuryInfo:
        """Look up injury status and compute discount."""
        inj_df = self.db.get_player_injuries(
            player_name=player_name, season=season, week=target_week,
        )
        info = InjuryInfo()
        if not inj_df.empty:
            row = inj_df.iloc[0]
            info.game_status = str(row.get("game_status", "")) if pd.notna(row.get("game_status")) else None
            info.practice_status = str(row.get("practice_status", "")) if pd.notna(row.get("practice_status")) else None
            info.discount = _injury_discount(info.game_status)
        return info

    def _get_td_probability(
        self,
        player_name: str,
        season: int,
        target_week: int,
        position: str,
    ) -> float:
        """Estimate TD probability from red-zone and end-zone target share.

        Returns a multiplier applied to the projected TD count.
        """
        adv = self.db.get_player_advanced_stats(player_name, season)
        if adv.empty:
            return 1.0

        recent = adv[adv["week"] < target_week].tail(4)
        if recent.empty:
            return 1.0

        rz_targets = int(recent["red_zone_targets"].sum())
        ez_targets = int(recent["end_zone_targets"].sum())
        total_targets = int(recent["targets"].sum())

        if total_targets == 0:
            return 1.0

        rz_share = rz_targets / total_targets
        ez_share = ez_targets / total_targets

        # Model: P(TD) = rz_share * 0.25 + ez_share * 0.45
        # Return as a multiplier against league-average TD rate
        td_prob = rz_share * 0.25 + ez_share * 0.45

        # Position-specific baseline TD rate approximations
        baseline_td_rates = {"WR": 0.05, "TE": 0.04, "RB": 0.08, "QB": 0.04}
        baseline = baseline_td_rates.get(position, 0.04)
        if baseline == 0:
            return 1.0

        # Cap the multiplier to avoid extreme values
        multiplier = td_prob / baseline
        return max(0.5, min(2.5, multiplier))

    def _get_defensive_matchup(
        self,
        player_name: str,
        season: int,
        target_week: int,
        position: str,
    ) -> float:
        """Query the defensive matchup adjustment factor.

        Returns a multiplier centered around 1.0 (e.g. 1.10 means the
        defence is 10 % worse than average against this position).
        """
        try:
            # Determine the player's team (opponent's defence)
            hist = self.db.get_player_history(player_name, num_weeks=1)
            if hist.empty:
                return 1.0
            player_team = hist.iloc[0]["opponent"]
            if not player_team or player_team == "TBD":
                return 1.0

            matchup = self.db.get_defensive_matchup_stats(
                team=player_team, position=position, season=season, weeks=4,
            )
            if matchup is None:
                return 1.0
            # matchup is a dict with 'epa_allowed_per_play' and 'fp_allowed_per_game'
            fp_allowed = matchup.get("fp_allowed_per_game")
            if fp_allowed is None:
                return 1.0

            # Compare to position average (league-wide ~15-20 for WR, ~10-12 for RB/TE)
            position_avg_fp = {"QB": 18.0, "RB": 12.0, "WR": 15.0, "TE": 8.0}
            avg = position_avg_fp.get(position, 12.0)
            if avg == 0:
                return 1.0

            ratio = fp_allowed / avg
            # Clamp to [0.8, 1.2] to avoid extreme adjustments
            return max(0.8, min(1.2, ratio))
        except Exception:
            logger.debug("Could not compute defensive matchup for %s", player_name, exc_info=True)
            return 1.0

    # ------------------------------------------------------------------
    # Adjustment methods
    # ------------------------------------------------------------------

    def _adjust_volume(
        self,
        proj: dict,
        vol: VolumeFeatures,
        position: str,
    ) -> dict:
        """Apply volume-based adjustments to stat projections."""
        adj = {}

        if position in ("WR", "TE") and vol.target_share is not None:
            league_avg = _get_league_avg_target_share(position)
            if league_avg > 0:
                volume_mult = vol.target_share / league_avg
                # Apply to receiving volume
                if "receiving_yards" in proj and proj["receiving_yards"]:
                    adj["receiving_yards"] = int(proj["receiving_yards"] * volume_mult)
                if "receptions" in proj and proj["receptions"]:
                    adj["receptions"] = int(proj["receptions"] * volume_mult)

        if position == "RB" and vol.snap_pct is not None:
            # RB: project carries based on snap share
            avg_snap_pct = 0.45  # league RB average
            snap_mult = vol.snap_pct / avg_snap_pct if avg_snap_pct > 0 else 1.0
            if "rushing_yards" in proj and proj["rushing_yards"]:
                adj["rushing_yards"] = int(proj["rushing_yards"] * snap_mult)

        # Snap % influences all positions' opportunity
        if vol.snap_pct is not None and position != "QB":
            avg_snap = {"RB": 0.45, "WR": 0.80, "TE": 0.65}.get(position, 0.70)
            opp_mult = vol.snap_pct / avg_snap if avg_snap > 0 else 1.0
            # Blend with target share mult if already applied
            if "receiving_yards" in adj:
                adj["receiving_yards"] = int(adj["receiving_yards"] * opp_mult)
            elif "receiving_yards" in proj and proj["receiving_yards"]:
                adj["receiving_yards"] = int(proj["receiving_yards"] * opp_mult)

        return adj

    def _adjust_efficiency(
        self,
        proj: dict,
        eff: EfficiencyFeatures,
        position: str,
    ) -> dict:
        """Apply efficiency adjustments based on NGS."""
        adj = {}

        # QB: adjust passing yards via CPOE
        if position == "QB" and eff.cpoe is not None:
            eff_delta = eff.cpoe * 0.15  # 15% weight
            if "passing_yards" in proj and proj["passing_yards"]:
                adj["passing_yards"] = int(proj["passing_yards"] * (1 + eff_delta))

        # WR/TE: separation + YAC above expectation
        if position in ("WR", "TE"):
            eff_delta = 0.0
            if eff.yac_above_expectation is not None:
                eff_delta += eff.yac_above_expectation * 0.02  # 2% per yard over
            if eff.avg_separation is not None:
                eff_delta += eff.avg_separation * 0.01  # 1% per yard of separation
            eff_delta = max(-0.15, min(0.15, eff_delta))  # clamp
            if eff_delta != 0 and "receiving_yards" in proj and proj["receiving_yards"]:
                adj["receiving_yards"] = int(proj["receiving_yards"] * (1 + eff_delta))

        # RB: YPC via rush yards over expected per attempt
        if position == "RB" and eff.ryoe_per_att is not None:
            eff_delta = eff.ryoe_per_att * 0.15  # 15% weight
            eff_delta = max(-0.15, min(0.15, eff_delta))
            if eff_delta != 0 and "rushing_yards" in proj and proj["rushing_yards"]:
                adj["rushing_yards"] = int(proj["rushing_yards"] * (1 + eff_delta))

        return adj

    def _adjust_td_projection(
        self,
        proj: dict,
        td_mult: float,
        position: str,
    ) -> dict:
        """Adjust TD projections using red-zone probability multiplier."""
        adj = {}
        if td_mult == 1.0:
            return adj

        if position in ("WR", "TE") and "receiving_tds" in proj:
            adj["receiving_tds"] = round(proj["receiving_tds"] * td_mult, 1)
        if position == "RB":
            if "rushing_tds" in proj:
                adj["rushing_tds"] = round(proj["rushing_tds"] * td_mult, 1)
            if "receiving_tds" in proj:
                adj["receiving_tds"] = round(proj["receiving_tds"] * td_mult, 1)
        if position == "QB" and "passing_tds" in proj:
            adj["passing_tds"] = round(proj["passing_tds"] * td_mult, 1)

        return adj

    def _apply_final_discounts(self, proj: dict) -> dict:
        """Apply injury discount and defensive matchup factor."""
        discount = proj.get("injury_discount", 1.0)
        if discount <= 0:
            # Player is out — zero out all stats
            for k in ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
                      "receiving_yards", "receiving_tds", "receptions"):
                proj[k] = 0
            return proj

        matchup_factor = proj.get("matchup_factor", 1.0)

        td_keys = {"passing_tds", "rushing_tds", "receiving_tds"}
        int_keys = {"passing_yards", "rushing_yards", "receiving_yards", "receptions"}
        for k in td_keys | int_keys:
            if k in proj and proj[k]:
                val = proj[k] * discount * matchup_factor
                proj[k] = round(val, 1) if k in td_keys else int(round(val))

        return proj


# ======================================================================
# HistoricalProjectionModel (original, kept for backward compat)
# ======================================================================


class HistoricalProjectionModel:
    """Generate projections based on player's historical performance."""

    def __init__(self, db: Optional[FFPyDatabase] = None):
        """
        Initialize the projection model.

        Args:
            db: Database instance. If None, creates new connection.
        """
        self.db = db if db else FFPyDatabase()

    def generate_projections(
        self,
        season: int,
        week: int,
        lookback_weeks: int = 4,
        recent_weight: float = 0.6,
    ) -> pd.DataFrame:
        """
        Generate projections for all players based on recent history.

        Args:
            season: Target season
            week: Target week to project
            lookback_weeks: Number of past weeks to analyze (default: 4)
            recent_weight: Weight for recent games vs older games (0-1)

        Returns:
            DataFrame with projections for all players
        """
        # Get list of all active players from recent weeks
        recent_data = self.db.get_actual_stats(season=season, week=max(1, week - lookback_weeks))

        if recent_data.empty:
            print(f"No historical data found for season {season}")
            return pd.DataFrame()

        players = recent_data[["player", "position", "team"]].drop_duplicates()

        projections = []

        for _, player_row in players.iterrows():
            player_name = player_row["player"]

            # Get player's recent performance
            projection = self.project_player(
                player_name=player_name,
                season=season,
                target_week=week,
                lookback_weeks=lookback_weeks,
                recent_weight=recent_weight,
            )

            if projection:
                projections.append(projection)

        return pd.DataFrame(projections)

    def project_player(
        self,
        player_name: str,
        season: int,
        target_week: int,
        lookback_weeks: int = 4,
        recent_weight: float = 0.6,
    ) -> Optional[dict]:
        """
        Generate projection for a single player.

        Args:
            player_name: Player name
            season: Target season
            target_week: Week to project
            lookback_weeks: Number of weeks to look back
            recent_weight: Weight for recent performance

        Returns:
            Dictionary with projected stats, or None if insufficient data
        """
        # Get player's recent history
        history = self.db.get_player_history(player_name, num_weeks=lookback_weeks)

        if history.empty or len(history) < 2:
            return None  # Not enough data

        # Calculate weighted averages (recent games matter more)
        weights = self._calculate_weights(len(history), recent_weight)

        projection = {
            "player": player_name,
            "team": history.iloc[0]["team"],
            "position": history.iloc[0]["position"],
            "week": target_week,
            "opponent": "TBD",
        }

        # Calculate weighted averages for each stat
        stats_to_project = [
            "actual_points",
            "passing_yards",
            "passing_tds",
            "rushing_yards",
            "rushing_tds",
            "receiving_yards",
            "receiving_tds",
            "receptions",
        ]

        for stat in stats_to_project:
            if stat in history.columns:
                values = history[stat].fillna(0).values
                if len(values) > 0:
                    weighted_avg = np.average(values[: len(weights)], weights=weights[: len(values)])

                    # Add variance for realism (-5% to +5%)
                    variance = np.random.uniform(0.95, 1.05)
                    projected_value = weighted_avg * variance

                    # Store projected value
                    if stat == "actual_points":
                        projection["projected_points"] = round(projected_value, 1)
                    else:
                        if "tds" in stat:
                            projection[stat] = round(projected_value, 1)
                        else:
                            projection[stat] = int(projected_value)

        # Calculate consistency score
        projection["consistency"] = round(history["actual_points"].std(), 1)

        return projection

    def _calculate_weights(self, n: int, recent_weight: float) -> np.ndarray:
        """
        Calculate weights for historical games.

        More recent games get higher weight.

        Args:
            n: Number of games
            recent_weight: How much to weight recent games (0-1)

        Returns:
            Array of weights (most recent first)
        """
        if n == 1:
            return np.array([1.0])

        # Exponential decay: most recent = 1.0, oldest = (1-recent_weight)
        weights = np.array([(1 - recent_weight) + recent_weight * (i / (n - 1)) for i in range(n)])

        # Reverse so most recent is first
        weights = weights[::-1]

        # Normalize
        return weights / weights.sum()

    def get_player_projection(self, player_name: str, season: int, week: int) -> Optional[pd.DataFrame]:
        """
        Get projection for a specific player with context.

        Args:
            player_name: Player name
            season: Season year
            week: Week number

        Returns:
            DataFrame with projection and recent history
        """
        projection = self.project_player(player_name, season, week)

        if not projection:
            return None

        # Get recent history for context
        history = self.db.get_player_history(player_name, num_weeks=5)

        result = pd.DataFrame([projection])
        result["recent_avg"] = history["actual_points"].mean() if not history.empty else 0
        result["recent_high"] = history["actual_points"].max() if not history.empty else 0
        result["recent_low"] = history["actual_points"].min() if not history.empty else 0

        return result
