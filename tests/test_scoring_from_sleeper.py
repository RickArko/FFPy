"""Tests for ScoringConfig.from_sleeper."""

from ffpy.scoring import ScoringConfig


def test_from_sleeper_ppr() -> None:
    config = ScoringConfig.from_sleeper({"rec": 1, "pass_td": 4, "pass_yd": 0.04})
    assert config.reception_points == 1.0
    assert config.name == "PPR"


def test_from_sleeper_half_ppr() -> None:
    config = ScoringConfig.from_sleeper({"rec": 0.5})
    assert config.reception_points == 0.5
    assert config.name == "Half-PPR"


def test_from_sleeper_standard() -> None:
    config = ScoringConfig.from_sleeper({"rec": 0})
    assert config.reception_points == 0.0
    assert config.name == "Standard"
