"""
Scoring configuration and fantasy points calculation.

This module handles different fantasy football scoring systems (PPR, Half-PPR, Standard)
and provides utilities to convert player stats into fantasy points.
"""

import json
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ScoringConfig:
    """Fantasy football scoring configuration."""

    # Scoring type identifier
    name: str = "Standard"

    # Passing scoring
    passing_yards_per_point: float = 25.0  # 1 point per 25 yards
    passing_td_points: float = 4.0
    interception_points: float = -2.0
    passing_2pt_conversion: float = 2.0

    # Rushing scoring
    rushing_yards_per_point: float = 10.0  # 1 point per 10 yards
    rushing_td_points: float = 6.0
    rushing_2pt_conversion: float = 2.0

    # Receiving scoring
    receiving_yards_per_point: float = 10.0  # 1 point per 10 yards
    receiving_td_points: float = 6.0
    reception_points: float = 0.0  # PPR: 1.0, Half-PPR: 0.5, Standard: 0.0
    receiving_2pt_conversion: float = 2.0

    # Miscellaneous
    fumble_lost_points: float = -2.0
    fumble_recovered_td: float = 6.0

    # Bonus points (optional)
    bonus_settings: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def ppr(cls) -> "ScoringConfig":
        """
        Create a PPR (Point Per Reception) scoring configuration.

        Returns:
            ScoringConfig with PPR settings
        """
        return cls(
            name="PPR",
            reception_points=1.0,
        )

    @classmethod
    def half_ppr(cls) -> "ScoringConfig":
        """
        Create a Half-PPR scoring configuration.

        Returns:
            ScoringConfig with Half-PPR settings
        """
        return cls(
            name="Half-PPR",
            reception_points=0.5,
        )

    @classmethod
    def standard(cls) -> "ScoringConfig":
        """
        Create a Standard (non-PPR) scoring configuration.

        Returns:
            ScoringConfig with Standard settings
        """
        return cls(
            name="Standard",
            reception_points=0.0,
        )

    @classmethod
    def from_dict(cls, config: Dict) -> "ScoringConfig":
        """
        Create ScoringConfig from dictionary.

        Args:
            config: Dictionary with scoring settings

        Returns:
            ScoringConfig instance
        """
        return cls(**config)

    @classmethod
    def from_json_file(cls, file_path: str) -> "ScoringConfig":
        """
        Load scoring configuration from JSON file.

        Args:
            file_path: Path to JSON configuration file

        Returns:
            ScoringConfig instance
        """
        with open(file_path, "r") as f:
            config = json.load(f)
        return cls.from_dict(config)

    def to_dict(self) -> Dict:
        """
        Convert scoring configuration to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "passing_yards_per_point": self.passing_yards_per_point,
            "passing_td_points": self.passing_td_points,
            "interception_points": self.interception_points,
            "passing_2pt_conversion": self.passing_2pt_conversion,
            "rushing_yards_per_point": self.rushing_yards_per_point,
            "rushing_td_points": self.rushing_td_points,
            "rushing_2pt_conversion": self.rushing_2pt_conversion,
            "receiving_yards_per_point": self.receiving_yards_per_point,
            "receiving_td_points": self.receiving_td_points,
            "reception_points": self.reception_points,
            "receiving_2pt_conversion": self.receiving_2pt_conversion,
            "fumble_lost_points": self.fumble_lost_points,
            "fumble_recovered_td": self.fumble_recovered_td,
            "bonus_settings": self.bonus_settings,
        }

    def to_json_file(self, file_path: str):
        """
        Save scoring configuration to JSON file.

        Args:
            file_path: Path to save JSON file
        """
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def __repr__(self) -> str:
        """String representation."""
        return f"ScoringConfig(name='{self.name}', reception_points={self.reception_points})"


def calculate_fantasy_points(
    stats: Dict[str, float],
    scoring_config: ScoringConfig,
) -> float:
    """
    Calculate fantasy points for a player based on their stats and scoring configuration.

    Args:
        stats: Dictionary of player stats
            - passing_yards: int
            - passing_tds: int
            - interceptions: int
            - rushing_yards: int
            - rushing_tds: int
            - receiving_yards: int
            - receiving_tds: int
            - receptions: int
            - fumbles_lost: int (optional)
            - fumbles_recovered_td: int (optional)

        scoring_config: Scoring configuration to use

    Returns:
        Total fantasy points

    Example:
        >>> stats = {
        ...     "passing_yards": 300,
        ...     "passing_tds": 2,
        ...     "interceptions": 1,
        ...     "rushing_yards": 50,
        ...     "rushing_tds": 1,
        ... }
        >>> config = ScoringConfig.ppr()
        >>> points = calculate_fantasy_points(stats, config)
        >>> print(f"{points:.1f}")
        29.0
    """
    points = 0.0

    # Passing points
    if "passing_yards" in stats and stats["passing_yards"] > 0:
        points += stats["passing_yards"] / scoring_config.passing_yards_per_point

    if "passing_tds" in stats and stats["passing_tds"] > 0:
        points += stats["passing_tds"] * scoring_config.passing_td_points

    if "interceptions" in stats and stats["interceptions"] > 0:
        points += stats["interceptions"] * scoring_config.interception_points

    # Rushing points
    if "rushing_yards" in stats and stats["rushing_yards"] > 0:
        points += stats["rushing_yards"] / scoring_config.rushing_yards_per_point

    if "rushing_tds" in stats and stats["rushing_tds"] > 0:
        points += stats["rushing_tds"] * scoring_config.rushing_td_points

    # Receiving points
    if "receiving_yards" in stats and stats["receiving_yards"] > 0:
        points += stats["receiving_yards"] / scoring_config.receiving_yards_per_point

    if "receiving_tds" in stats and stats["receiving_tds"] > 0:
        points += stats["receiving_tds"] * scoring_config.receiving_td_points

    if "receptions" in stats and stats["receptions"] > 0:
        points += stats["receptions"] * scoring_config.reception_points

    # Fumbles
    if "fumbles_lost" in stats and stats["fumbles_lost"] > 0:
        points += stats["fumbles_lost"] * scoring_config.fumble_lost_points

    if "fumbles_recovered_td" in stats and stats["fumbles_recovered_td"] > 0:
        points += stats["fumbles_recovered_td"] * scoring_config.fumble_recovered_td

    # 2-point conversions
    if "passing_2pt" in stats and stats["passing_2pt"] > 0:
        points += stats["passing_2pt"] * scoring_config.passing_2pt_conversion

    if "rushing_2pt" in stats and stats["rushing_2pt"] > 0:
        points += stats["rushing_2pt"] * scoring_config.rushing_2pt_conversion

    if "receiving_2pt" in stats and stats["receiving_2pt"] > 0:
        points += stats["receiving_2pt"] * scoring_config.receiving_2pt_conversion

    return round(points, 2)


def calculate_points_from_projection(
    projection: Dict[str, float],
    scoring_config: ScoringConfig,
) -> float:
    """
    Calculate fantasy points from a projection dictionary.

    This is a convenience wrapper around calculate_fantasy_points that
    handles the common case of projection dictionaries.

    Args:
        projection: Projection dictionary (from HistoricalProjectionModel)
        scoring_config: Scoring configuration

    Returns:
        Projected fantasy points
    """
    # Extract stats from projection
    stats = {
        key: projection.get(key, 0)
        for key in [
            "passing_yards",
            "passing_tds",
            "interceptions",
            "rushing_yards",
            "rushing_tds",
            "receiving_yards",
            "receiving_tds",
            "receptions",
            "fumbles_lost",
        ]
    }

    return calculate_fantasy_points(stats, scoring_config)
