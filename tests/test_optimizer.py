"""Unit tests for lineup optimizer components."""

import pytest

from ffpy.optimizer import (
    LineupResult,
    Player,
    PlayerStatus,
    RosterConstraints,
)


class TestPlayer:
    """Tests for Player class."""

    def test_player_creation(self):
        """Test basic player creation."""
        player = Player(
            name="Patrick Mahomes",
            position="QB",
            team="KC",
            projected_points=25.5,
        )

        assert player.name == "Patrick Mahomes"
        assert player.position == "QB"
        assert player.team == "KC"
        assert player.projected_points == 25.5
        assert player.status == PlayerStatus.AVAILABLE

    def test_player_with_detailed_projections(self):
        """Test player with detailed stat projections."""
        player = Player(
            name="Christian McCaffrey",
            position="RB",
            team="SF",
            projected_points=22.3,
            passing_yards=0,
            rushing_yards=95,
            rushing_tds=1.2,
            receiving_yards=45,
            receiving_tds=0.3,
            receptions=5.5,
        )

        assert player.rushing_yards == 95
        assert player.receptions == 5.5

    def test_player_is_available_healthy(self):
        """Test is_available for healthy player."""
        player = Player(
            name="Test Player",
            position="WR",
            team="DAL",
            projected_points=15.0,
            status=PlayerStatus.AVAILABLE,
        )

        assert player.is_available() is True

    def test_player_is_available_questionable(self):
        """Test is_available for questionable player."""
        player = Player(
            name="Test Player",
            position="WR",
            team="DAL",
            projected_points=15.0,
            status=PlayerStatus.QUESTIONABLE,
        )

        assert player.is_available() is True

    def test_player_is_not_available_injured(self):
        """Test is_available for injured player."""
        player = Player(
            name="Injured Player",
            position="RB",
            team="NYJ",
            projected_points=0.0,
            status=PlayerStatus.INJURED,
        )

        assert player.is_available() is False

    def test_player_is_not_available_out(self):
        """Test is_available for OUT player."""
        player = Player(
            name="Out Player",
            position="TE",
            team="MIA",
            projected_points=0.0,
            status=PlayerStatus.OUT,
        )

        assert player.is_available() is False

    def test_player_is_not_available_bye(self):
        """Test is_available for player on bye."""
        player = Player(
            name="Bye Player",
            position="QB",
            team="BUF",
            projected_points=0.0,
            status=PlayerStatus.BYE,
        )

        assert player.is_available() is False

    def test_player_is_not_available_locked(self):
        """Test is_available for locked player."""
        player = Player(
            name="Locked Player",
            position="WR",
            team="PHI",
            projected_points=18.0,
            status=PlayerStatus.LOCKED,
        )

        assert player.is_available() is False

    def test_player_repr(self):
        """Test string representation."""
        player = Player(
            name="Travis Kelce",
            position="TE",
            team="KC",
            projected_points=16.7,
        )

        repr_str = repr(player)
        assert "Travis Kelce" in repr_str
        assert "TE" in repr_str
        assert "16.7" in repr_str


class TestRosterConstraints:
    """Tests for RosterConstraints class."""

    def test_standard_preset(self):
        """Test standard roster constraints preset."""
        constraints = RosterConstraints.standard()

        assert constraints.positions["QB"] == 1
        assert constraints.positions["RB"] == 2
        assert constraints.positions["WR"] == 2
        assert constraints.positions["TE"] == 1
        assert constraints.positions["K"] == 1
        assert constraints.positions["DST"] == 1
        assert constraints.num_flex == 1
        assert "RB" in constraints.flex_positions
        assert "WR" in constraints.flex_positions
        assert "TE" in constraints.flex_positions
        assert constraints.total_starters == 9  # 7 positions + 1 FLEX

    def test_superflex_preset(self):
        """Test superflex roster constraints preset."""
        constraints = RosterConstraints.superflex()

        assert constraints.positions["QB"] == 1
        assert constraints.num_flex == 1
        assert "QB" in constraints.flex_positions  # QB can be flexed

    def test_no_kicker_dst_preset(self):
        """Test no kicker/DST preset."""
        constraints = RosterConstraints.no_kicker_dst()

        assert "K" not in constraints.positions
        assert "DST" not in constraints.positions
        assert constraints.positions["QB"] == 1
        assert constraints.positions["RB"] == 2
        assert constraints.total_starters == 7  # 5 positions + 1 FLEX

    def test_custom_constraints(self):
        """Test custom roster constraints."""
        constraints = RosterConstraints(
            positions={"QB": 2, "RB": 2, "WR": 3, "TE": 1},
            flex_positions=["RB", "WR"],
            num_flex=2,
            max_players_per_team=4,
        )

        assert constraints.positions["QB"] == 2
        assert constraints.positions["WR"] == 3
        assert constraints.num_flex == 2
        assert constraints.max_players_per_team == 4
        assert constraints.total_starters == 10  # 8 positions + 2 FLEX

    def test_total_starters_auto_calculation(self):
        """Test that total_starters is calculated automatically."""
        constraints = RosterConstraints(
            positions={"QB": 1, "RB": 2, "WR": 2},
            num_flex=1,
        )

        assert constraints.total_starters == 6  # 5 + 1

    def test_total_starters_manual_override(self):
        """Test manual override of total_starters."""
        constraints = RosterConstraints(
            positions={"QB": 1, "RB": 2},
            num_flex=0,
            total_starters=10,  # Manual override
        )

        assert constraints.total_starters == 10

    def test_locked_in_players(self):
        """Test locked_in constraint."""
        constraints = RosterConstraints.standard()
        constraints.locked_in = {"Patrick Mahomes", "Travis Kelce"}

        assert "Patrick Mahomes" in constraints.locked_in
        assert "Travis Kelce" in constraints.locked_in
        assert len(constraints.locked_in) == 2

    def test_locked_out_players(self):
        """Test locked_out constraint."""
        constraints = RosterConstraints.standard()
        constraints.locked_out = {"Injured Player", "Suspended Player"}

        assert "Injured Player" in constraints.locked_out
        assert len(constraints.locked_out) == 2

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        original = RosterConstraints(
            positions={"QB": 1, "RB": 2},
            flex_positions=["RB", "WR"],
            num_flex=1,
            locked_in={"Player A", "Player B"},
        )

        config_dict = original.to_dict()
        restored = RosterConstraints.from_dict(config_dict)

        assert restored.positions == original.positions
        assert restored.flex_positions == original.flex_positions
        assert restored.num_flex == original.num_flex
        assert restored.locked_in == original.locked_in

    def test_get_required_positions(self):
        """Test get_required_positions method."""
        constraints = RosterConstraints(
            positions={"QB": 1, "RB": 2, "WR": 3},
            num_flex=0,
        )

        required = constraints.get_required_positions()

        assert required["QB"] == 1
        assert required["RB"] == 2
        assert required["WR"] == 3
        assert len(required) == 3

    def test_repr(self):
        """Test string representation."""
        constraints = RosterConstraints(
            positions={"QB": 1, "RB": 2},
            flex_positions=["RB", "WR"],
            num_flex=1,
        )

        repr_str = repr(constraints)
        assert "QB:1" in repr_str
        assert "RB:2" in repr_str
        assert "FLEX" in repr_str


class TestLineupResult:
    """Tests for LineupResult class."""

    def test_lineup_result_creation(self):
        """Test basic lineup result creation."""
        starters = [
            Player("QB1", "QB", "KC", 25.0),
            Player("RB1", "RB", "SF", 20.0),
            Player("WR1", "WR", "BUF", 18.0),
        ]

        bench = [
            Player("RB2", "RB", "DAL", 12.0),
            Player("WR2", "WR", "MIA", 10.0),
        ]

        result = LineupResult(
            starters=starters,
            bench=bench,
            total_points=63.0,
            points_by_position={"QB": 25.0, "RB": 20.0, "WR": 18.0},
            solve_time_ms=15.5,
            is_optimal=True,
        )

        assert len(result.starters) == 3
        assert len(result.bench) == 2
        assert result.total_points == 63.0
        assert result.is_optimal is True
        assert result.solve_time_ms == 15.5

    def test_lineup_result_with_improvement(self):
        """Test lineup result with improvement metric."""
        result = LineupResult(
            starters=[],
            bench=[],
            total_points=120.0,
            points_by_position={},
            solve_time_ms=10.0,
            is_optimal=True,
            improvement_vs_current=15.5,
        )

        assert result.improvement_vs_current == 15.5

    def test_get_starters_by_position(self):
        """Test grouping starters by position."""
        starters = [
            Player("QB1", "QB", "KC", 25.0),
            Player("RB1", "RB", "SF", 20.0),
            Player("RB2", "RB", "DAL", 18.0),
            Player("WR1", "WR", "BUF", 16.0),
            Player("WR2", "WR", "MIA", 14.0),
        ]

        result = LineupResult(
            starters=starters,
            bench=[],
            total_points=93.0,
            points_by_position={},
            solve_time_ms=5.0,
            is_optimal=True,
        )

        by_position = result.get_starters_by_position()

        assert len(by_position["QB"]) == 1
        assert len(by_position["RB"]) == 2
        assert len(by_position["WR"]) == 2
        assert by_position["QB"][0].name == "QB1"

    def test_repr(self):
        """Test string representation."""
        result = LineupResult(
            starters=[Player("P1", "QB", "KC", 25.0)],
            bench=[],
            total_points=125.5,
            points_by_position={},
            solve_time_ms=12.3,
            is_optimal=True,
        )

        repr_str = repr(result)
        assert "125.5" in repr_str
        assert "optimal=True" in repr_str


class TestPlayerStatus:
    """Tests for PlayerStatus enum."""

    def test_player_status_values(self):
        """Test that all status values exist."""
        assert PlayerStatus.AVAILABLE.value == "available"
        assert PlayerStatus.INJURED.value == "injured"
        assert PlayerStatus.BYE.value == "bye"
        assert PlayerStatus.QUESTIONABLE.value == "questionable"
        assert PlayerStatus.OUT.value == "out"
        assert PlayerStatus.LOCKED.value == "locked"


class TestLineupOptimizer:
    """Tests for LineupOptimizer class."""

    def create_sample_players(self) -> list:
        """Create sample players for testing."""
        return [
            # QBs
            Player("Patrick Mahomes", "QB", "KC", 25.5),
            Player("Josh Allen", "QB", "BUF", 24.2),
            Player("Jalen Hurts", "QB", "PHI", 23.1),
            # RBs
            Player("Christian McCaffrey", "RB", "SF", 22.3),
            Player("Austin Ekeler", "RB", "WAS", 18.7),
            Player("Bijan Robinson", "RB", "ATL", 17.5),
            Player("James Cook", "RB", "BUF", 15.2),
            # WRs
            Player("Tyreek Hill", "WR", "MIA", 19.8),
            Player("CeeDee Lamb", "WR", "DAL", 18.5),
            Player("Justin Jefferson", "WR", "MIN", 18.2),
            Player("Amon-Ra St. Brown", "WR", "DET", 16.9),
            Player("Stefon Diggs", "WR", "HOU", 14.3),
            # TEs
            Player("Travis Kelce", "TE", "KC", 16.5),
            Player("Mark Andrews", "TE", "BAL", 14.2),
            Player("George Kittle", "TE", "SF", 13.1),
            # K
            Player("Justin Tucker", "K", "BAL", 9.5),
            # DST
            Player("49ers DST", "DST", "SF", 10.2),
        ]

    def test_basic_optimization(self):
        """Test basic lineup optimization."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        assert result.is_optimal
        assert len(result.starters) == 9  # 1 QB + 2 RB + 2 WR + 1 TE + 1 FLEX + 1 K + 1 DST
        assert result.total_points > 0
        assert result.solve_time_ms > 0

    def test_optimal_lineup_selects_best_players(self):
        """Test that optimizer selects highest-projected players."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        # Should select Patrick Mahomes (highest QB)
        qb_names = [p.name for p in result.starters if p.position == "QB"]
        assert "Patrick Mahomes" in qb_names

        # Should select top 2 RBs
        rb_names = [p.name for p in result.starters if p.position == "RB"]
        assert "Christian McCaffrey" in rb_names
        assert "Austin Ekeler" in rb_names

    def test_flex_position_handling(self):
        """Test that FLEX position is filled correctly."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        # Count total RB + WR + TE
        flex_eligible = [p for p in result.starters if p.position in ["RB", "WR", "TE"]]

        # Should have: 2 RB + 2 WR + 1 TE + 1 FLEX = 6 total
        assert len(flex_eligible) == 6

    def test_locked_in_player(self):
        """Test that locked-in players are forced to start."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()

        # Lock in a suboptimal QB
        constraints.locked_in = {"Jalen Hurts"}

        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players)

        # Jalen Hurts should be in lineup even though Mahomes/Allen are better
        starter_names = [p.name for p in result.starters]
        assert "Jalen Hurts" in starter_names

    def test_locked_out_player(self):
        """Test that locked-out players are forced to sit."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()

        # Lock out the best RB
        constraints.locked_out = {"Christian McCaffrey"}

        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players)

        # McCaffrey should not be in lineup
        starter_names = [p.name for p in result.starters]
        assert "Christian McCaffrey" not in starter_names

        # But should be on bench
        bench_names = [p.name for p in result.bench]
        assert "Christian McCaffrey" in bench_names

    def test_injured_players_excluded(self):
        """Test that injured players are automatically excluded."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()

        # Mark best player as injured
        players[0].status = PlayerStatus.INJURED  # Patrick Mahomes

        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players)

        # Mahomes should not be in lineup or bench
        all_names = [p.name for p in result.starters + result.bench]
        assert "Patrick Mahomes" not in all_names

    def test_team_stack_limits(self):
        """Test max players per team constraint."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()

        # Limit to max 2 players per team
        constraints.max_players_per_team = 2

        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players)

        # Count players per team
        team_counts = {}
        for player in result.starters:
            team_counts[player.team] = team_counts.get(player.team, 0) + 1

        # No team should have more than 2 players
        for team, count in team_counts.items():
            assert count <= 2, f"Team {team} has {count} players (max 2)"

    def test_no_kicker_dst_constraints(self):
        """Test optimization without kicker/DST."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.no_kicker_dst()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        assert len(result.starters) == 7  # 1 QB + 2 RB + 2 WR + 1 TE + 1 FLEX

        # Should have no kicker or DST
        positions = [p.position for p in result.starters]
        assert "K" not in positions
        assert "DST" not in positions

    def test_improvement_calculation(self):
        """Test improvement calculation vs current lineup."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()

        # Create a suboptimal current lineup
        current_lineup = [
            players[2],  # Jalen Hurts (QB) - 3rd best
            players[5],  # Bijan Robinson (RB) - 3rd best
            players[6],  # James Cook (RB) - 4th best
            players[10],  # Amon-Ra St. Brown (WR)
            players[11],  # Stefon Diggs (WR) - 5th best
            players[14],  # George Kittle (TE) - 3rd best
            players[4],  # Austin Ekeler (FLEX)
            players[15],  # Justin Tucker (K)
            players[16],  # 49ers DST
        ]

        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players, current_lineup=current_lineup)

        assert result.improvement_vs_current is not None
        assert result.improvement_vs_current > 0  # Optimal should be better

    def test_bench_sorting(self):
        """Test that bench is sorted by projected points."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        # Bench should be sorted descending by points
        bench_points = [p.projected_points for p in result.bench]
        assert bench_points == sorted(bench_points, reverse=True)

    def test_analyze_lineup_output(self):
        """Test lineup analysis formatting."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)
        analysis = optimizer.analyze_lineup(result)

        # Check output contains key elements
        assert "OPTIMAL LINEUP" in analysis
        assert "Total Projected Points" in analysis
        assert "Solve Time" in analysis
        assert "TOP BENCH OPTIONS" in analysis

    def test_no_available_players_error(self):
        """Test error when no players are available."""
        from ffpy.optimizer import LineupOptimizer

        # All players injured
        players = [
            Player("Injured QB", "QB", "KC", 25.0, status=PlayerStatus.INJURED),
            Player("Injured RB", "RB", "SF", 20.0, status=PlayerStatus.OUT),
        ]

        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        with pytest.raises(ValueError, match="No available players"):
            optimizer.optimize(players)

    def test_insufficient_position_players_error(self):
        """Test error when not enough players for required positions."""
        from ffpy.optimizer import LineupOptimizer

        # Only 1 QB when we need 1 QB
        players = [
            Player("Only QB", "QB", "KC", 25.0),
            # No RBs, WRs, TEs, etc.
        ]

        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        with pytest.raises(ValueError, match="No available players for required position"):
            optimizer.optimize(players)

    def test_points_by_position(self):
        """Test points_by_position breakdown."""
        from ffpy.optimizer import LineupOptimizer

        players = self.create_sample_players()
        constraints = RosterConstraints.standard()
        optimizer = LineupOptimizer(constraints)

        result = optimizer.optimize(players)

        # Should have points for each position
        assert "QB" in result.points_by_position
        assert "RB" in result.points_by_position
        assert "WR" in result.points_by_position
        assert "TE" in result.points_by_position

        # QB points should match the selected QB's projection
        qb_points = result.points_by_position["QB"]
        qb_in_lineup = [p for p in result.starters if p.position == "QB"][0]
        assert qb_points == qb_in_lineup.projected_points
