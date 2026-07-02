"""Tests for college fantasy scoring."""

from ffpy.cfb_scoring import CfbScoringConfig, calculate_cfb_fantasy_points


def test_college_standard_qb_scoring():
    config = CfbScoringConfig.college_standard()
    stats = {
        "passing_yards": 280,
        "passing_tds": 3,
        "passing_interceptions": 1,
        "rushing_yards": 45,
        "rushing_tds": 1,
    }
    points = calculate_cfb_fantasy_points(stats, config)
    # 280/20 + 3*4 + (-2) + 45/10 + 6 = 14 + 12 - 2 + 4.5 + 6 = 34.5
    assert points == 34.5


def test_fcs_discount_applied():
    config = CfbScoringConfig.college_standard()
    stats = {"passing_yards": 200, "passing_tds": 2}
    full = calculate_cfb_fantasy_points(stats, config)
    discounted = calculate_cfb_fantasy_points(stats, config, opponent_classification="fcs", fcs_discount=0.75)
    assert discounted == round(full * 0.75, 2)


def test_dst_scoring_points_allowed_tier():
    config = CfbScoringConfig.college_standard()
    stats = {
        "sacks": 3,
        "interceptions": 1,
        "fumbles_recovered": 1,
        "defensive_tds": 0,
        "safeties": 0,
        "points_allowed": 10,
    }
    points = calculate_cfb_fantasy_points(stats, config, is_dst=True)
    # 3 + 2 + 2 + 4 (7-13 tier) = 11
    assert points == 11.0
