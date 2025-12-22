"""Unit tests for lineup optimizer components."""

import pytest
from ffpy.optimizer import (
    Player,
    PlayerStatus,
    RosterConstraints,
    LineupResult,
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
