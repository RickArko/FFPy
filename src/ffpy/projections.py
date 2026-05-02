"""
Projection model based on historical player performance.

This module generates fantasy projections by analyzing each player's
recent actual performance and applying statistical models.
"""

from typing import Optional

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase


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
