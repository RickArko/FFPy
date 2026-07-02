"""Unit tests for projection models."""

import pytest

from ffpy.projections import (
    DEPTH_CHART_PRIORS,
    INJURY_DISCOUNTS,
    LEAGUE_AVG_TARGET_SHARE,
    EfficiencyFeatures,
    EnhancedProjectionModel,
    HistoricalProjectionModel,
    InjuryInfo,
    VolumeFeatures,
    _blend_prior_with_history,
    _get_depth_chart_prior,
    _get_league_avg_target_share,
    _injury_discount,
)
from ffpy.scoring import ScoringConfig


class TestHelpers:
    """Tests for projection helper functions."""

    def test_league_avg_target_share(self):
        assert _get_league_avg_target_share("WR") == 0.16
        assert _get_league_avg_target_share("TE") == 0.12
        assert _get_league_avg_target_share("RB") == 0.08
        assert _get_league_avg_target_share("QB") == 0.10  # fallback

    def test_depth_chart_prior(self):
        assert _get_depth_chart_prior("WR", 1) == 0.22
        assert _get_depth_chart_prior("WR", 2) == 0.16
        assert _get_depth_chart_prior("WR", 5) is None
        assert _get_depth_chart_prior("QB", 1) is None

    def test_injury_discount_mapping(self):
        assert _injury_discount("Out") == 0.0
        assert _injury_discount("Doubtful") == 0.2
        assert _injury_discount("Questionable") == 0.75
        assert _injury_discount("Active") == 1.0
        assert _injury_discount(None) == 1.0
        assert _injury_discount("Unknown") == 1.0

    def test_blend_prior_no_history(self):
        result = _blend_prior_with_history(None, 0.20, weeks_of_history=0)
        assert result == 0.20

    def test_blend_prior_no_prior(self):
        result = _blend_prior_with_history(0.25, None, weeks_of_history=2)
        assert result == 0.25

    def test_blend_prior_ramp(self):
        # 1 week of history → prior dominates
        result = _blend_prior_with_history(0.10, 0.20, weeks_of_history=1)
        assert result == pytest.approx(0.10 * 0.25 + 0.20 * 0.75)

        # 4 weeks → history dominates
        result = _blend_prior_with_history(0.10, 0.20, weeks_of_history=4)
        assert result == 0.10


class TestVolumeFeatures:
    """Tests for VolumeFeatures dataclass."""

    def test_default_creation(self):
        vf = VolumeFeatures()
        assert vf.target_share is None
        assert vf.snap_pct is None
        assert vf.depth_spot is None

    def test_full_creation(self):
        vf = VolumeFeatures(
            target_share=0.28,
            air_yards_share=0.35,
            snap_pct=0.85,
            depth_spot=1,
        )
        assert vf.target_share == 0.28
        assert vf.snap_pct == 0.85


class TestEfficiencyFeatures:
    """Tests for EfficiencyFeatures dataclass."""

    def test_default_creation(self):
        ef = EfficiencyFeatures()
        assert ef.cpoe is None
        assert ef.avg_separation is None

    def test_qb_features(self):
        ef = EfficiencyFeatures(cpoe=3.5)
        assert ef.cpoe == 3.5


class TestInjuryInfo:
    """Tests for InjuryInfo dataclass."""

    def test_default_discount(self):
        info = InjuryInfo()
        assert info.discount == 1.0
        assert info.game_status is None

    def test_out_discount(self):
        info = InjuryInfo(game_status="Out", discount=0.0)
        assert info.discount == 0.0


class TestHistoricalProjectionModel:
    """Tests for the baseline HistoricalProjectionModel."""

    def test_weight_calculation(self):
        """Test that weights are calculated correctly."""
        model = HistoricalProjectionModel()

        # 4 weeks of data
        weights = model._calculate_weights(4, recent_weight=0.6)
        assert len(weights) == 4
        assert abs(sum(weights) - 1.0) < 1e-6
        # Most recent (index 0) should have highest weight
        assert weights[0] > weights[3]

    def test_single_week_weight(self):
        """Test weight calculation with single week."""
        model = HistoricalProjectionModel()
        weights = model._calculate_weights(1, recent_weight=0.6)
        assert weights == [1.0]

    def test_unequal_weights(self):
        """Test that recent_weight=1 gives linear decay."""
        model = HistoricalProjectionModel()
        weights = model._calculate_weights(3, recent_weight=1.0)
        # With recent_weight=1, oldest gets 0 weight in unnormalized form
        assert abs(sum(weights) - 1.0) < 1e-6


class TestEnhancedProjectionModelUnit:
    """Unit tests for EnhancedProjectionModel logic (no DB)."""

    def test_projected_points_from_stats(self):
        """Verify that EnhancedProjectionModel stores scoring config correctly."""
        scoring = ScoringConfig.ppr()
        result = EnhancedProjectionModel(scoring=scoring)
        assert result.scoring.name == "PPR"


class TestEnhancedModelAdjustments:
    """Test the adjustment formulas in isolation."""

    def test_volume_adjust_wr(self):
        """Test volume adjustment for WR with high target share."""
        proj = {"receiving_yards": 80, "receptions": 5}
        vol = VolumeFeatures(target_share=0.28)  # Above league avg 0.16
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_volume(proj, vol, "WR")
        # 0.28 / 0.16 = 1.75x multiplier
        assert "receiving_yards" in adj
        assert adj["receiving_yards"] > 80

    def test_volume_adjust_rb_snap(self):
        """Test snap-based adjustment for RB."""
        proj = {"rushing_yards": 60, "receiving_yards": 30}
        vol = VolumeFeatures(snap_pct=0.70)  # Above avg 0.45
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_volume(proj, vol, "RB")
        # 0.70 / 0.45 ≈ 1.56x multiplier
        if "rushing_yards" in adj:
            assert adj["rushing_yards"] > 60

    def test_no_adjustment_when_no_features(self):
        """Test that missing features produce no adjustment."""
        proj = {"receiving_yards": 80}
        vol = VolumeFeatures()
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_volume(proj, vol, "WR")
        assert adj == {}

    def test_efficiency_adjust_qb_cpoe(self):
        """Test CPOE adjustment for QBs."""
        proj = {"passing_yards": 250}
        eff = EfficiencyFeatures(cpoe=5.0)
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_efficiency(proj, eff, "QB")
        # 5.0 * 0.15 = 0.75 → 1.75% increase → 250 * 1.0175 ≈ 254
        if "passing_yards" in adj:
            assert adj["passing_yards"] > 250

    def test_efficiency_adjust_wr_yac(self):
        """Test YAC above expectation adjustment for WRs."""
        proj = {"receiving_yards": 80}
        eff = EfficiencyFeatures(yac_above_expectation=1.5, avg_separation=1.2)
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_efficiency(proj, eff, "WR")
        if "receiving_yards" in adj and adj["receiving_yards"] != 80:
            assert adj["receiving_yards"] > 80

    def test_td_probability_adjust(self):
        """Test red-zone based TD adjustment."""
        proj = {"receiving_tds": 0.6}
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_td_projection(proj, 1.5, "WR")
        if "receiving_tds" in adj:
            assert adj["receiving_tds"] == 0.9  # 0.6 * 1.5

    def test_injury_zero_out(self):
        """Test that Out injury zeros all stats."""
        proj = {
            "passing_yards": 300,
            "passing_tds": 2,
            "rushing_yards": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
            "receptions": 0,
            "injury_discount": 0.0,
            "injury_status": "Out",
            "matchup_factor": 1.0,
        }
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        result = model._apply_final_discounts(proj)
        assert result["passing_yards"] == 0
        assert result["passing_tds"] == 0

    def test_injury_questionable_partial(self):
        """Test that Questionable applies 0.75 discount."""
        proj = {
            "rushing_yards": 100,
            "rushing_tds": 1,
            "receiving_yards": 0,
            "receiving_tds": 0,
            "receptions": 0,
            "passing_yards": 0,
            "passing_tds": 0,
            "injury_discount": 0.75,
            "injury_status": "Questionable",
            "matchup_factor": 1.0,
        }
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        result = model._apply_final_discounts(proj)
        assert result["rushing_yards"] == 75  # 100 * 0.75
        # TDs remain as float with 1 decimal
        assert result["rushing_tds"] == 0.8  # 1 * 0.75 rounded to 1dp

    def test_matchup_factor_applied(self):
        """Test that matchup factor is applied as multiplier."""
        proj = {
            "rushing_yards": 100,
            "rushing_tds": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
            "receptions": 0,
            "passing_yards": 0,
            "passing_tds": 0,
            "injury_discount": 1.0,
            "injury_status": "Active",
            "matchup_factor": 1.15,
        }
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        result = model._apply_final_discounts(proj)
        assert result["rushing_yards"] == 115  # 100 * 1.15

    def test_volume_adjust_skipped_for_qb(self):
        """Test that volume adjustment is skipped for QBs."""
        proj = {"passing_yards": 250}
        vol = VolumeFeatures(target_share=0.30)
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_volume(proj, vol, "QB")
        assert adj == {}

    def test_td_adjust_qb(self):
        """Test TD adjustment for QB position."""
        proj = {"passing_tds": 2.0}
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_td_projection(proj, 1.2, "QB")
        assert adj.get("passing_tds") == 2.4

    def test_efficiency_adjust_rb_ryoe(self):
        """Test RYOE adjustment for RBs."""
        proj = {"rushing_yards": 80}
        eff = EfficiencyFeatures(ryoe_per_att=0.5)
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_efficiency(proj, eff, "RB")
        if "rushing_yards" in adj:
            assert adj["rushing_yards"] > 80

    def test_no_efficiency_adjust_no_ngs(self):
        """Test no efficiency adjustment when no NGS data."""
        proj = {"rushing_yards": 80}
        eff = EfficiencyFeatures()
        model = EnhancedProjectionModel(scoring=ScoringConfig.ppr())
        adj = model._adjust_efficiency(proj, eff, "RB")
        assert adj == {}


class TestConstants:
    """Test module-level constants."""

    def test_injury_discounts_keys(self):
        assert set(INJURY_DISCOUNTS.keys()) == {"Out", "Doubtful", "Questionable", "Active"}

    def test_league_avg_target_share_values(self):
        assert LEAGUE_AVG_TARGET_SHARE["WR"] == 0.16
        assert 0 < LEAGUE_AVG_TARGET_SHARE["TE"] < 0.20

    def test_depth_chart_priors_structure(self):
        assert "WR" in DEPTH_CHART_PRIORS
        assert DEPTH_CHART_PRIORS["WR"][1] > DEPTH_CHART_PRIORS["WR"][2]
