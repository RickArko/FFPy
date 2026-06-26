"""
Lineup optimization for fantasy football.

This module provides tools to optimize fantasy football lineups using
constraint-based optimization (Integer Linear Programming).
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from pulp import LpVariable


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

    # DFS salary (optional)
    salary: Optional[int] = None

    # Detailed projections (for display)
    passing_yards: Optional[float] = None
    passing_tds: Optional[float] = None
    rushing_yards: Optional[float] = None
    rushing_tds: Optional[float] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[float] = None
    receptions: Optional[float] = None

    @property
    def floor(self) -> float:
        """Lower-bound projection (projected - consistency)."""
        if self.consistency is not None and self.consistency > 0:
            return max(0.0, self.projected_points - self.consistency)
        return self.projected_points * 0.7

    @property
    def ceiling(self) -> float:
        """Upper-bound projection (projected + consistency)."""
        if self.consistency is not None and self.consistency > 0:
            return self.projected_points + self.consistency
        return self.projected_points * 1.3

    @property
    def value_score(self) -> Optional[float]:
        """Projected points per $1000 salary (DFS value)."""
        if self.salary is not None and self.salary > 0:
            return self.projected_points / self.salary * 1000
        return None

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

    # Salary cap (DFS mode)
    max_salary: Optional[int] = None  # Salary cap in $ (e.g., 50000 for DraftKings)

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
        optimize_for: str = "projected",
        stack_bonus: float = 0.0,
    ) -> LineupResult:
        """
        Optimize lineup to maximize projected points.

        Args:
            players: List of available players
            current_lineup: Optional current lineup for comparison
            verbose: Print solver output
            optimize_for: Objective strategy:
                - ``"projected"``: maximize projected points (default)
                - ``"floor"``: maximize floor (projected - consistency)
                - ``"ceiling"``: maximize ceiling (projected + consistency)
                - ``"value"``: maximize projected points per $1000 salary
            stack_bonus: Extra points added when a QB and WR/TE from the
                same team are both selected (0 = disabled).

        Returns:
            LineupResult with optimal lineup

        Raises:
            ValueError: If no feasible solution exists
        """
        try:
            from pulp import (
                PULP_CBC_CMD,
                LpMaximize,
                LpProblem,
                LpStatus,
                LpVariable,
                lpSum,
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

        # Objective: Choose the optimization target
        if optimize_for == "floor":
            objective = lpSum([player.floor * x[player.name] for player in available_players])
        elif optimize_for == "ceiling":
            objective = lpSum([player.ceiling * x[player.name] for player in available_players])
        elif optimize_for == "value":
            # Use projected_points / salary * 1000; fall back to projected if no salary
            objective = lpSum([
                (player.value_score if player.value_score is not None else player.projected_points)
                * x[player.name]
                for player in available_players
            ])
        else:
            objective = lpSum([player.projected_points * x[player.name] for player in available_players])

        # Add stack preference bonus
        if stack_bonus > 0:
            objective += self._add_stack_preference(prob, available_players, x, stack_bonus)

        # Set objective
        prob += objective

        # Add constraints
        self._add_position_constraints(prob, available_players, x)
        self._add_flex_constraints(prob, available_players, x)
        self._add_total_starters_constraint(prob, available_players, x)
        self._add_player_locks(prob, available_players, x)
        self._add_team_limits(prob, available_players, x)
        self._add_salary_cap(prob, available_players, x)

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

        # Calculate total projected points (always from projected_points, not objective)
        total_points = sum(p.projected_points for p in starters)

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

    def _add_salary_cap(self, prob, players: List[Player], x: Dict[str, "LpVariable"]):
        """Add salary cap constraint for DFS optimization."""
        from pulp import lpSum

        if self.constraints.max_salary is None:
            return

        players_with_salary = [p for p in players if p.salary is not None]
        if not players_with_salary:
            return  # Silently skip if no salary data

        prob += (
            lpSum([p.salary * x[p.name] for p in players_with_salary]) <= self.constraints.max_salary,
            "salary_cap",
        )

    def _add_stack_preference(
        self,
        prob,
        players: List[Player],
        x: Dict[str, "LpVariable"],
        bonus: float,
    ):
        """Add a small objective bonus when a QB and a skill player from the
        same team are both selected.

        This is modelled with auxiliary binary variables per team that indicate
        whether a QB-WR/TE stack exists on that team.

        Returns the bonus expression to add to the objective.
        """
        from pulp import LpAffineExpression, lpSum

        bonus_expr = LpAffineExpression()
        teams = set(p.team for p in players if p.team)

        for team in teams:
            qbs = [p for p in players if p.team == team and p.position == "QB"]
            skill = [p for p in players if p.team == team and p.position in ("WR", "TE")]

            if not qbs or not skill:
                continue

            # Auxiliary: stack_exists = 1 if at least one QB and one WR/TE selected
            has_qb = LpVariable(f"stack_qb_{team}", cat="Binary")
            has_skill = LpVariable(f"stack_skill_{team}", cat="Binary")
            stack_exists = LpVariable(f"stack_{team}", cat="Binary")

            # has_qb <= sum(x[qb])  (if any QB on this team is started)
            prob += has_qb <= lpSum([x[qb.name] for qb in qbs]), f"stack_qb_def_{team}"
            # has_qb >= (1/len(qbs)) * sum(x[qb]) -- if any QB started, has_qb = 1
            prob += has_qb >= (1.0 / len(qbs)) * lpSum([x[qb.name] for qb in qbs]), f"stack_qb_trigger_{team}"

            prob += has_skill <= lpSum([x[s.name] for s in skill]), f"stack_skill_def_{team}"
            prob += has_skill >= (1.0 / len(skill)) * lpSum([x[s.name] for s in skill]), f"stack_skill_trigger_{team}"

            # stack_exists = has_qb AND has_skill
            prob += stack_exists <= has_qb, f"stack_and1_{team}"
            prob += stack_exists <= has_skill, f"stack_and2_{team}"
            prob += stack_exists >= has_qb + has_skill - 1, f"stack_and3_{team}"

            bonus_expr += bonus * stack_exists

        return bonus_expr

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
