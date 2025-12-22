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


class LineupOptimizer:
    """
    Optimize fantasy football lineups using Integer Linear Programming.

    This class uses PuLP to solve the lineup optimization problem:
    - Maximize: Sum of projected points for selected players
    - Subject to: Position requirements, roster constraints, player locks

    The optimization uses binary decision variables (start=1, sit=0) and
    solves using the CBC solver (included with PuLP).
    """

    def __init__(self, constraints: RosterConstraints):
        """
        Initialize lineup optimizer.

        Args:
            constraints: Roster constraints (positions, FLEX, etc.)
        """
        self.constraints = constraints

    def optimize(
        self,
        players: List[Player],
        current_lineup: Optional[List[Player]] = None,
        verbose: bool = False,
    ) -> LineupResult:
        """
        Optimize lineup to maximize projected points.

        Args:
            players: List of available players
            current_lineup: Optional current lineup for comparison
            verbose: Print solver output

        Returns:
            LineupResult with optimal lineup

        Raises:
            ValueError: If no feasible solution exists
        """
        try:
            from pulp import (
                LpMaximize,
                LpProblem,
                LpVariable,
                lpSum,
                LpStatus,
                PULP_CBC_CMD,
                value,
            )
        except ImportError:
            raise ImportError("PuLP is required for lineup optimization. Install with: uv add pulp")

        import time

        start_time = time.time()

        # Filter to only available players
        available_players = [p for p in players if p.is_available()]

        if not available_players:
            raise ValueError("No available players to optimize")

        # Create optimization problem
        prob = LpProblem("Lineup_Optimization", LpMaximize)

        # Decision variables: binary (1 = start, 0 = sit)
        x = {player.name: LpVariable(f"start_{player.name}", cat="Binary") for player in available_players}

        # Objective: Maximize total projected points
        prob += lpSum([player.projected_points * x[player.name] for player in available_players])

        # Add constraints
        self._add_position_constraints(prob, available_players, x)
        self._add_flex_constraints(prob, available_players, x)
        self._add_total_starters_constraint(prob, available_players, x)
        self._add_player_locks(prob, available_players, x)
        self._add_team_limits(prob, available_players, x)

        # Solve
        solver = PULP_CBC_CMD(msg=verbose)
        prob.solve(solver)

        solve_time_ms = (time.time() - start_time) * 1000

        # Check solution status
        if LpStatus[prob.status] != "Optimal":
            raise ValueError(f"No optimal solution found. Status: {LpStatus[prob.status]}")

        # Extract results
        starters = []
        bench = []

        for player in available_players:
            if x[player.name].varValue == 1:
                starters.append(player)
            else:
                bench.append(player)

        # Sort bench by projected points (descending)
        bench.sort(key=lambda p: p.projected_points, reverse=True)

        # Calculate points by position
        points_by_position = {}
        for player in starters:
            if player.position not in points_by_position:
                points_by_position[player.position] = 0.0
            points_by_position[player.position] += player.projected_points

        # Calculate total points
        total_points = value(prob.objective)

        # Calculate improvement if current lineup provided
        improvement = None
        if current_lineup:
            current_points = sum(p.projected_points for p in current_lineup)
            improvement = total_points - current_points

        return LineupResult(
            starters=starters,
            bench=bench,
            total_points=total_points,
            points_by_position=points_by_position,
            solve_time_ms=solve_time_ms,
            is_optimal=True,
            improvement_vs_current=improvement,
        )

    def _add_position_constraints(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """
        Add position requirement constraints (e.g., exactly 1 QB, at least 2 RB, etc.).

        For positions that are FLEX-eligible, we use >= (at least) instead of ==
        to allow extra players in FLEX spots. For non-FLEX positions, we use ==.

        Args:
            prob: PuLP problem instance
            players: List of available players
            x: Dictionary of decision variables
        """
        from pulp import lpSum

        for position, count in self.constraints.positions.items():
            # Get players eligible for this position
            eligible = [p for p in players if p.position == position]

            if not eligible and count > 0:
                raise ValueError(f"No available players for required position: {position}")

            # For FLEX-eligible positions, use >= (minimum)
            # For other positions, use == (exact)
            if position in self.constraints.flex_positions:
                # Minimum requirement (allows extras for FLEX)
                prob += (
                    lpSum([x[p.name] for p in eligible]) >= count,
                    f"{position}_min_requirement",
                )
            else:
                # Exact requirement
                prob += (
                    lpSum([x[p.name] for p in eligible]) == count,
                    f"{position}_exact_requirement",
                )

    def _add_flex_constraints(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """
        Add FLEX position constraints.

        FLEX allows any player from flex_positions to fill remaining spots.
        The total selected from flex-eligible positions should equal the
        base requirements plus the FLEX spots.

        For example, with RB=2, WR=2, TE=1, FLEX=1:
        - Total RB+WR+TE selected should equal 2+2+1+1 = 6

        Args:
            prob: PuLP problem instance
            players: List of available players
            x: Dictionary of decision variables
        """
        from pulp import lpSum

        if self.constraints.num_flex == 0:
            return  # No FLEX spots

        # Get all players eligible for FLEX
        flex_eligible = [p for p in players if p.position in self.constraints.flex_positions]

        if not flex_eligible:
            raise ValueError("No players eligible for FLEX positions")

        # Calculate total required from flex-eligible positions
        # This is the sum of base position requirements + FLEX spots
        base_requirements = sum(
            self.constraints.positions.get(pos, 0) for pos in self.constraints.flex_positions
        )
        total_required = base_requirements + self.constraints.num_flex

        # Add constraint: total from flex positions >= base + flex
        # We use >= instead of == to allow position constraints to be exact
        prob += (
            lpSum([x[p.name] for p in flex_eligible]) == total_required,
            "flex_total_constraint",
        )

    def _add_total_starters_constraint(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """
        Add constraint for total number of starters.

        This prevents the optimizer from selecting more players than allowed.

        Args:
            prob: PuLP problem instance
            players: List of available players
            x: Dictionary of decision variables
        """
        from pulp import lpSum

        if self.constraints.total_starters is not None:
            prob += (
                lpSum([x[p.name] for p in players]) == self.constraints.total_starters,
                "total_starters_constraint",
            )

    def _add_player_locks(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """
        Add constraints for locked-in and locked-out players.

        Args:
            prob: PuLP problem instance
            players: List of available players
            x: Dictionary of decision variables
        """
        # Force locked-in players to start
        for player_name in self.constraints.locked_in:
            if player_name in x:
                prob += x[player_name] == 1, f"lock_in_{player_name}"

        # Force locked-out players to sit
        for player_name in self.constraints.locked_out:
            if player_name in x:
                prob += x[player_name] == 0, f"lock_out_{player_name}"

    def _add_team_limits(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """
        Add constraints for max players per team (stack limits).

        Args:
            prob: PuLP problem instance
            players: List of available players
            x: Dictionary of decision variables
        """
        from pulp import lpSum

        if self.constraints.max_players_per_team is None:
            return  # No stack limits

        # Group players by team
        teams = set(p.team for p in players)

        for team in teams:
            team_players = [p for p in players if p.team == team]

            prob += (
                lpSum([x[p.name] for p in team_players]) <= self.constraints.max_players_per_team,
                f"team_limit_{team}",
            )

    def analyze_lineup(self, result: LineupResult) -> str:
        """
        Generate a human-readable analysis of the optimized lineup.

        Args:
            result: LineupResult from optimization

        Returns:
            Formatted string with lineup analysis
        """
        lines = []
        lines.append("=" * 60)
        lines.append("OPTIMAL LINEUP")
        lines.append("=" * 60)

        # Group starters by position
        by_position = result.get_starters_by_position()

        for position in sorted(by_position.keys()):
            players = by_position[position]
            lines.append(f"\n{position}:")
            for player in sorted(players, key=lambda p: p.projected_points, reverse=True):
                lines.append(f"  • {player.name:25} {player.team:4} {player.projected_points:5.1f} pts")

        # Summary
        lines.append("\n" + "-" * 60)
        lines.append(f"Total Projected Points: {result.total_points:.1f}")
        lines.append(f"Solve Time: {result.solve_time_ms:.1f} ms")

        if result.improvement_vs_current is not None:
            lines.append(
                f"Improvement: {result.improvement_vs_current:+.1f} pts "
                f"({result.improvement_vs_current / (result.total_points - result.improvement_vs_current) * 100:+.1f}%)"
            )

        # Top bench options
        if result.bench:
            lines.append("\n" + "=" * 60)
            lines.append("TOP BENCH OPTIONS")
            lines.append("=" * 60)
            for player in result.bench[:5]:  # Top 5 bench
                lines.append(
                    f"  • {player.name:25} {player.position:3} {player.team:4} "
                    f"{player.projected_points:5.1f} pts"
                )

        lines.append("=" * 60)

        return "\n".join(lines)
