"""Tests for constraints_from_sleeper_slots."""

from ffpy.optimizer import RosterConstraints
from ffpy.sleeper_import import constraints_from_sleeper_slots


def test_constraints_standard_flex() -> None:
    constraints = constraints_from_sleeper_slots(
        {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1}
    )
    assert isinstance(constraints, RosterConstraints)
    assert constraints.positions["QB"] == 1
    assert constraints.positions["RB"] == 2
    assert constraints.num_flex == 1
    assert constraints.flex_positions == ["RB", "WR", "TE"]
    assert "FLEX" not in constraints.positions


def test_constraints_superflex_op() -> None:
    constraints = constraints_from_sleeper_slots(
        {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "OP": 1, "K": 1, "DST": 1}
    )
    assert constraints.num_flex == 1
    assert "QB" in constraints.flex_positions
    assert constraints.flex_positions == ["QB", "RB", "WR", "TE"]


def test_constraints_multiple_flex() -> None:
    constraints = constraints_from_sleeper_slots({"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2})
    assert constraints.num_flex == 2
