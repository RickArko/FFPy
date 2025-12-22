"""
Lineup optimization for fantasy football.

This module provides tools to optimize fantasy football lineups using
constraint-based optimization (Integer Linear Programming).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import json


class PlayerStatus(Enum):
    """Player availability status."""

    AVAILABLE = "available"
    INJURED = "injured"
    BYE = "bye"
    QUESTIONABLE = "questionable"
    OUT = "out"
    LOCKED = "locked"  # Already played this week


@dataclass
class Player:
    """
    Represents a fantasy football player with projection data.
    """

    name: str
    position: str  # QB, RB, WR, TE, K, DST
    team: str
    projected_points: float
    status: PlayerStatus = PlayerStatus.AVAILABLE

    # Optional fields
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    consistency: Optional[float] = None  # Standard deviation of recent scores

    # Detailed projections (for display)
    passing_yards: Optional[float] = None
    passing_tds: Optional[float] = None
    rushing_yards: Optional[float] = None
    rushing_tds: Optional[float] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[float] = None
    receptions: Optional[float] = None

    def is_available(self) -> bool:
        """Check if player is available to be started."""
        return self.status in [PlayerStatus.AVAILABLE, PlayerStatus.QUESTIONABLE]

    def __repr__(self) -> str:
        """String representation."""
        return f"Player(name='{self.name}', pos={self.position}, proj={self.projected_points:.1f})"


@dataclass
class RosterConstraints:
    """
    Defines the roster constraints for lineup optimization.

    This includes position requirements (e.g., 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX)
    and other roster rules.
    """

    # Position requirements (number of starters needed)
    positions: Dict[str, int] = field(default_factory=dict)

    # FLEX configuration
    flex_positions: List[str] = field(default_factory=list)  # e.g., ['RB', 'WR', 'TE']
    num_flex: int = 0

    # Roster limits
    max_players_per_team: Optional[int] = None  # Stack limits (optional)
    total_starters: Optional[int] = None  # Auto-calculated if None

    # Player locks (force specific players in/out)
    locked_in: Set[str] = field(default_factory=set)  # Player names to force start
    locked_out: Set[str] = field(default_factory=set)  # Player names to force bench

    def __post_init__(self):
        """Calculate total starters if not provided."""
        if self.total_starters is None:
            self.total_starters = sum(self.positions.values()) + self.num_flex

    @classmethod
    def standard(cls) -> "RosterConstraints":
        """
        Create standard roster constraints (most common format).

        Lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE), 1 K, 1 DST

        Returns:
            RosterConstraints with standard settings
        """
        return cls(
            positions={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1},
            flex_positions=["RB", "WR", "TE"],
            num_flex=1,
        )

    @classmethod
    def no_kicker_dst(cls) -> "RosterConstraints":
        """
        Create constraints without kicker/defense (skill positions only).

        Lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE)

        Returns:
            RosterConstraints without K/DST
        """
        return cls(
            positions={"QB": 1, "RB": 2, "WR": 2, "TE": 1},
            flex_positions=["RB", "WR", "TE"],
            num_flex=1,
        )

    @classmethod
    def superflex(cls) -> "RosterConstraints":
        """
        Create superflex roster constraints (QB can play FLEX).

        Lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 SUPERFLEX (any position), 1 K, 1 DST

        Returns:
            RosterConstraints with superflex
        """
        return cls(
            positions={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1},
            flex_positions=["QB", "RB", "WR", "TE"],  # QB can be flexed
            num_flex=1,
        )

    @classmethod
    def from_dict(cls, config: Dict) -> "RosterConstraints":
        """
        Create RosterConstraints from dictionary.

        Args:
            config: Dictionary with constraint settings

        Returns:
            RosterConstraints instance
        """
        # Handle sets serialization
        if "locked_in" in config and isinstance(config["locked_in"], list):
            config["locked_in"] = set(config["locked_in"])
        if "locked_out" in config and isinstance(config["locked_out"], list):
            config["locked_out"] = set(config["locked_out"])

        return cls(**config)

    @classmethod
    def from_json_file(cls, file_path: str) -> "RosterConstraints":
        """
        Load roster constraints from JSON file.

        Args:
            file_path: Path to JSON configuration file

        Returns:
            RosterConstraints instance
        """
        with open(file_path, "r") as f:
            config = json.load(f)
        return cls.from_dict(config)

    def to_dict(self) -> Dict:
        """
        Convert roster constraints to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "positions": self.positions,
            "flex_positions": self.flex_positions,
            "num_flex": self.num_flex,
            "max_players_per_team": self.max_players_per_team,
            "total_starters": self.total_starters,
            "locked_in": list(self.locked_in),
            "locked_out": list(self.locked_out),
        }

    def to_json_file(self, file_path: str):
        """
        Save roster constraints to JSON file.

        Args:
            file_path: Path to save JSON file
        """
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def get_required_positions(self) -> Dict[str, int]:
        """
        Get all position requirements including FLEX.

        Returns:
            Dictionary of position counts
        """
        return self.positions.copy()

    def __repr__(self) -> str:
        """String representation."""
        pos_str = ", ".join([f"{pos}:{count}" for pos, count in self.positions.items()])
        flex_str = f", FLEX({','.join(self.flex_positions)}):{self.num_flex}" if self.num_flex > 0 else ""
        return f"RosterConstraints({pos_str}{flex_str})"


@dataclass
class LineupResult:
    """
    Result of lineup optimization.
    """

    # Optimal starting lineup
    starters: List[Player]

    # Bench players (sorted by projected points)
    bench: List[Player]

    # Total projected points
    total_points: float

    # Breakdown by position
    points_by_position: Dict[str, float]

    # Optimization metadata
    solve_time_ms: float
    is_optimal: bool
    improvement_vs_current: Optional[float] = None  # If comparing to existing lineup

    def get_starters_by_position(self) -> Dict[str, List[Player]]:
        """
        Group starters by position.

        Returns:
            Dictionary mapping position to list of players
        """
        result = {}
        for player in self.starters:
            if player.position not in result:
                result[player.position] = []
            result[player.position].append(player)
        return result

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"LineupResult(total_points={self.total_points:.1f}, "
            f"starters={len(self.starters)}, "
            f"bench={len(self.bench)}, "
            f"optimal={self.is_optimal})"
        )
