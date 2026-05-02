"""Unit tests for scoring configuration and fantasy points calculation."""

from ffpy.scoring import ScoringConfig, calculate_fantasy_points


class TestScoringConfig:
    """Tests for ScoringConfig class."""

    def test_ppr_preset(self):
        """Test PPR preset configuration."""
        config = ScoringConfig.ppr()
        assert config.name == "PPR"
        assert config.reception_points == 1.0
        assert config.passing_td_points == 4.0
        assert config.rushing_td_points == 6.0

    def test_half_ppr_preset(self):
        """Test Half-PPR preset configuration."""
        config = ScoringConfig.half_ppr()
        assert config.name == "Half-PPR"
        assert config.reception_points == 0.5

    def test_standard_preset(self):
        """Test Standard preset configuration."""
        config = ScoringConfig.standard()
        assert config.name == "Standard"
        assert config.reception_points == 0.0

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        original = ScoringConfig.ppr()
        config_dict = original.to_dict()
        restored = ScoringConfig.from_dict(config_dict)

        assert restored.name == original.name
        assert restored.reception_points == original.reception_points
        assert restored.passing_td_points == original.passing_td_points

    def test_custom_scoring(self):
        """Test custom scoring configuration."""
        config = ScoringConfig(
            name="Custom",
            passing_td_points=6.0,  # 6 points per passing TD
            reception_points=1.5,  # 1.5 PPR
        )

        assert config.name == "Custom"
        assert config.passing_td_points == 6.0
        assert config.reception_points == 1.5


class TestCalculateFantasyPoints:
    """Tests for calculate_fantasy_points function."""

    def test_quarterback_scoring_standard(self):
        """Test QB scoring in standard format."""
        config = ScoringConfig.standard()
        stats = {
            "passing_yards": 300,  # 300 / 25 = 12 points
            "passing_tds": 2,  # 2 * 4 = 8 points
            "interceptions": 1,  # 1 * -2 = -2 points
            "rushing_yards": 20,  # 20 / 10 = 2 points
        }

        points = calculate_fantasy_points(stats, config)
        expected = 12.0 + 8.0 - 2.0 + 2.0
        assert points == expected

    def test_running_back_scoring_ppr(self):
        """Test RB scoring in PPR format."""
        config = ScoringConfig.ppr()
        stats = {
            "rushing_yards": 100,  # 100 / 10 = 10 points
            "rushing_tds": 1,  # 1 * 6 = 6 points
            "receiving_yards": 30,  # 30 / 10 = 3 points
            "receiving_tds": 0,
            "receptions": 5,  # 5 * 1 = 5 points (PPR)
        }

        points = calculate_fantasy_points(stats, config)
        expected = 10.0 + 6.0 + 3.0 + 5.0
        assert points == expected

    def test_wide_receiver_scoring_half_ppr(self):
        """Test WR scoring in Half-PPR format."""
        config = ScoringConfig.half_ppr()
        stats = {
            "receiving_yards": 120,  # 120 / 10 = 12 points
            "receiving_tds": 2,  # 2 * 6 = 12 points
            "receptions": 8,  # 8 * 0.5 = 4 points (Half-PPR)
        }

        points = calculate_fantasy_points(stats, config)
        expected = 12.0 + 12.0 + 4.0
        assert points == expected

    def test_tight_end_scoring_ppr(self):
        """Test TE scoring in PPR format."""
        config = ScoringConfig.ppr()
        stats = {
            "receiving_yards": 80,  # 80 / 10 = 8 points
            "receiving_tds": 1,  # 1 * 6 = 6 points
            "receptions": 6,  # 6 * 1 = 6 points (PPR)
        }

        points = calculate_fantasy_points(stats, config)
        expected = 8.0 + 6.0 + 6.0
        assert points == expected

    def test_fumbles_scoring(self):
        """Test fumble penalties."""
        config = ScoringConfig.standard()
        stats = {
            "rushing_yards": 100,  # 10 points
            "rushing_tds": 1,  # 6 points
            "fumbles_lost": 2,  # 2 * -2 = -4 points
        }

        points = calculate_fantasy_points(stats, config)
        expected = 10.0 + 6.0 - 4.0
        assert points == expected

    def test_zero_stats(self):
        """Test player with zero stats."""
        config = ScoringConfig.ppr()
        stats = {
            "passing_yards": 0,
            "passing_tds": 0,
            "rushing_yards": 0,
            "receiving_yards": 0,
        }

        points = calculate_fantasy_points(stats, config)
        assert points == 0.0

    def test_empty_stats(self):
        """Test with empty stats dictionary."""
        config = ScoringConfig.ppr()
        stats = {}

        points = calculate_fantasy_points(stats, config)
        assert points == 0.0

    def test_dual_threat_qb_ppr(self):
        """Test dual-threat QB (passing + rushing)."""
        config = ScoringConfig.ppr()
        stats = {
            "passing_yards": 275,  # 11 points
            "passing_tds": 3,  # 12 points
            "interceptions": 0,
            "rushing_yards": 50,  # 5 points
            "rushing_tds": 1,  # 6 points
        }

        points = calculate_fantasy_points(stats, config)
        expected = 11.0 + 12.0 + 5.0 + 6.0
        assert points == expected

    def test_two_point_conversions(self):
        """Test 2-point conversion scoring."""
        config = ScoringConfig.standard()
        stats = {
            "passing_yards": 0,
            "passing_2pt": 1,  # 2 points
            "rushing_2pt": 1,  # 2 points
        }

        points = calculate_fantasy_points(stats, config)
        expected = 2.0 + 2.0
        assert points == expected

    def test_custom_scoring_rules(self):
        """Test custom scoring configuration."""
        # 6 points per passing TD (instead of 4)
        config = ScoringConfig(
            name="Custom",
            passing_td_points=6.0,
            passing_yards_per_point=20.0,  # 1 point per 20 yards
        )

        stats = {
            "passing_yards": 300,  # 300 / 20 = 15 points
            "passing_tds": 2,  # 2 * 6 = 12 points
        }

        points = calculate_fantasy_points(stats, config)
        expected = 15.0 + 12.0
        assert points == expected

    def test_rounding(self):
        """Test that points are rounded correctly."""
        config = ScoringConfig.standard()
        stats = {
            "passing_yards": 333,  # 333 / 25 = 13.32
        }

        points = calculate_fantasy_points(stats, config)
        assert points == 13.32

    def test_negative_points_possible(self):
        """Test that negative total points are possible."""
        config = ScoringConfig.standard()
        stats = {
            "passing_yards": 50,  # 2 points
            "interceptions": 3,  # -6 points
            "fumbles_lost": 2,  # -4 points
        }

        points = calculate_fantasy_points(stats, config)
        assert points == -8.0
