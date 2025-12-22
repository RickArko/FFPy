"""
Example: Lineup Optimization with FFPy

This script demonstrates how to use the lineup optimizer to find the
optimal fantasy football lineup given a set of players and projections.
"""

from ffpy.optimizer import (
    LineupOptimizer,
    RosterConstraints,
    Player,
    PlayerStatus,
)


def example_1_basic_optimization():
    """Example 1: Basic lineup optimization with default constraints."""
    print("=" * 70)
    print("EXAMPLE 1: Basic Lineup Optimization")
    print("=" * 70)

    # Create sample players with projections
    players = [
        # Quarterbacks
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Josh Allen", "QB", "BUF", 24.2),
        Player("Jalen Hurts", "QB", "PHI", 23.1),
        # Running Backs
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("Austin Ekeler", "RB", "WAS", 18.7),
        Player("Bijan Robinson", "RB", "ATL", 17.5),
        Player("James Cook", "RB", "BUF", 15.2),
        # Wide Receivers
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5),
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Amon-Ra St. Brown", "WR", "DET", 16.9),
        Player("Stefon Diggs", "WR", "HOU", 14.3),
        # Tight Ends
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("Mark Andrews", "TE", "BAL", 14.2),
        Player("George Kittle", "TE", "SF", 13.1),
        # Kicker
        Player("Justin Tucker", "K", "BAL", 9.5),
        # Defense
        Player("49ers DST", "DST", "SF", 10.2),
    ]

    # Use standard roster constraints (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DST)
    constraints = RosterConstraints.standard()

    # Create optimizer
    optimizer = LineupOptimizer(constraints)

    # Optimize lineup
    result = optimizer.optimize(players)

    # Print results
    print(optimizer.analyze_lineup(result))
    print()


def example_2_player_locks():
    """Example 2: Force specific players to start or sit."""
    print("=" * 70)
    print("EXAMPLE 2: Player Locks (Force Start/Sit)")
    print("=" * 70)

    players = [
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Josh Allen", "QB", "BUF", 24.2),
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("Austin Ekeler", "RB", "WAS", 18.7),
        Player("Bijan Robinson", "RB", "ATL", 17.5),
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5),
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("Justin Tucker", "K", "BAL", 9.5),
        Player("49ers DST", "DST", "SF", 10.2),
    ]

    # Create constraints with player locks
    constraints = RosterConstraints.standard()
    constraints.locked_in = {"Josh Allen", "Travis Kelce"}  # Must start these players
    constraints.locked_out = {"Christian McCaffrey"}  # Must bench this player

    optimizer = LineupOptimizer(constraints)
    result = optimizer.optimize(players)

    print(optimizer.analyze_lineup(result))
    print(f"\nNote: Josh Allen and Travis Kelce are FORCED to start")
    print(f"Note: Christian McCaffrey is FORCED to sit (despite high projection)")
    print()


def example_3_injured_players():
    """Example 3: Handle injured and questionable players."""
    print("=" * 70)
    print("EXAMPLE 3: Injured & Questionable Players")
    print("=" * 70)

    players = [
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Josh Allen", "QB", "BUF", 24.2, status=PlayerStatus.INJURED),  # Injured!
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("Austin Ekeler", "RB", "WAS", 18.7, status=PlayerStatus.QUESTIONABLE),
        Player("Bijan Robinson", "RB", "ATL", 17.5),
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5, status=PlayerStatus.OUT),  # Out!
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Amon-Ra St. Brown", "WR", "DET", 16.9),
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("Justin Tucker", "K", "BAL", 9.5),
        Player("49ers DST", "DST", "SF", 10.2),
    ]

    constraints = RosterConstraints.standard()
    optimizer = LineupOptimizer(constraints)
    result = optimizer.optimize(players)

    print(optimizer.analyze_lineup(result))
    print(f"\nNote: Josh Allen (INJURED) and CeeDee Lamb (OUT) are automatically excluded")
    print(f"Note: Austin Ekeler (QUESTIONABLE) is still eligible to play")
    print()


def example_4_team_stack_limits():
    """Example 4: Limit players from same team (avoid stacking)."""
    print("=" * 70)
    print("EXAMPLE 4: Team Stack Limits")
    print("=" * 70)

    players = [
        # Lots of KC and SF players
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("George Kittle", "TE", "SF", 15.1),
        Player("Deebo Samuel", "WR", "SF", 17.8),
        # Other players
        Player("Josh Allen", "QB", "BUF", 24.2),
        Player("Austin Ekeler", "RB", "WAS", 18.7),
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5),
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Justin Tucker", "K", "BAL", 9.5),
        Player("49ers DST", "DST", "SF", 10.2),
    ]

    # Limit to max 2 players per team
    constraints = RosterConstraints.standard()
    constraints.max_players_per_team = 2

    optimizer = LineupOptimizer(constraints)
    result = optimizer.optimize(players)

    print(optimizer.analyze_lineup(result))

    # Count players per team
    team_counts = {}
    for player in result.starters:
        team_counts[player.team] = team_counts.get(player.team, 0) + 1

    print(f"\nTeam distribution:")
    for team, count in sorted(team_counts.items()):
        print(f"  {team}: {count} player(s)")
    print(f"\nNote: No team has more than 2 players (stack limit enforced)")
    print()


def example_5_no_kicker_dst():
    """Example 5: Optimize without kicker or defense."""
    print("=" * 70)
    print("EXAMPLE 5: No Kicker/Defense Format")
    print("=" * 70)

    players = [
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("Austin Ekeler", "RB", "WAS", 18.7),
        Player("Bijan Robinson", "RB", "ATL", 17.5),
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5),
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("Mark Andrews", "TE", "BAL", 14.2),
    ]

    # No kicker or defense
    constraints = RosterConstraints.no_kicker_dst()

    optimizer = LineupOptimizer(constraints)
    result = optimizer.optimize(players)

    print(optimizer.analyze_lineup(result))
    print(f"\nNote: Only skill positions (QB, RB, WR, TE) are selected")
    print()


def example_6_comparison_with_current():
    """Example 6: Compare optimal lineup vs current lineup."""
    print("=" * 70)
    print("EXAMPLE 6: Improvement vs Current Lineup")
    print("=" * 70)

    players = [
        Player("Patrick Mahomes", "QB", "KC", 25.5),
        Player("Josh Allen", "QB", "BUF", 24.2),
        Player("Christian McCaffrey", "RB", "SF", 22.3),
        Player("Austin Ekeler", "RB", "WAS", 18.7),
        Player("Bijan Robinson", "RB", "ATL", 17.5),
        Player("Tyreek Hill", "WR", "MIA", 19.8),
        Player("CeeDee Lamb", "WR", "DAL", 18.5),
        Player("Justin Jefferson", "WR", "MIN", 18.2),
        Player("Amon-Ra St. Brown", "WR", "DET", 16.9),
        Player("Travis Kelce", "TE", "KC", 16.5),
        Player("George Kittle", "TE", "SF", 13.1),
        Player("Justin Tucker", "K", "BAL", 9.5),
        Player("49ers DST", "DST", "SF", 10.2),
    ]

    # Suboptimal current lineup
    current_lineup = [
        players[1],  # Josh Allen (QB) - 2nd best
        players[4],  # Bijan Robinson (RB) - 3rd best
        players[5],  # Tyreek Hill (WR)
        players[7],  # Justin Jefferson (WR)
        players[8],  # Amon-Ra St. Brown (WR) - 4th best
        players[10],  # George Kittle (TE) - 2nd best
        players[3],  # Austin Ekeler (FLEX) - 2nd best RB
        players[11],  # Justin Tucker (K)
        players[12],  # 49ers DST
    ]

    constraints = RosterConstraints.standard()
    optimizer = LineupOptimizer(constraints)

    # Optimize with current lineup for comparison
    result = optimizer.optimize(players, current_lineup=current_lineup)

    print(optimizer.analyze_lineup(result))
    print()


if __name__ == "__main__":
    # Run all examples
    example_1_basic_optimization()
    example_2_player_locks()
    example_3_injured_players()
    example_4_team_stack_limits()
    example_5_no_kicker_dst()
    example_6_comparison_with_current()

    print("=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)
