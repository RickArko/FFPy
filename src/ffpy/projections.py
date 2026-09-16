"""Projection models.

Implementation lives in ``nfl_data.projections.model`` when nfl-data is installed.
This module re-exports the same names so sleeper-brain imports stay stable.
"""

from __future__ import annotations

try:
    from nfl_data.projections.model import (
        DEPTH_CHART_PRIORS,
        INJURY_DISCOUNTS,
        LEAGUE_AVG_TARGET_SHARE,
        EfficiencyFeatures,
        EnhancedProjectionModel,
        HistoricalProjectionModel,
        InjuryInfo,
        VolumeFeatures,
        position_fallback_projection,
    )
except ImportError:  # pragma: no cover - git pin without nfl-data
    from ffpy._projections_legacy import (
        DEPTH_CHART_PRIORS,
        INJURY_DISCOUNTS,
        LEAGUE_AVG_TARGET_SHARE,
        EfficiencyFeatures,
        EnhancedProjectionModel,
        HistoricalProjectionModel,
        InjuryInfo,
        VolumeFeatures,
        position_fallback_projection,
    )

__all__ = [
    "DEPTH_CHART_PRIORS",
    "INJURY_DISCOUNTS",
    "LEAGUE_AVG_TARGET_SHARE",
    "EfficiencyFeatures",
    "EnhancedProjectionModel",
    "HistoricalProjectionModel",
    "InjuryInfo",
    "VolumeFeatures",
    "position_fallback_projection",
]
