"""College fantasy football scoring (separate from NFL scoring.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from ffpy.scoring import ScoringConfig


@dataclass
class CfbScoringConfig(ScoringConfig):
    """College fantasy scoring with kicker and DST rules."""

    field_goal_points: float = 3.0
    extra_point_points: float = 1.0
    defense_sack_points: float = 1.0
    defense_interception_points: float = 2.0
    defense_fumble_recovery_points: float = 2.0
    defense_td_points: float = 6.0
    defense_safety_points: float = 2.0
    defense_points_allowed_tiers: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def college_standard(cls) -> "CfbScoringConfig":
        config_path = Path(__file__).parent.parent.parent / "config" / "scoring" / "college_standard.json"
        if config_path.exists():
            return cls.from_json_file(config_path)
        return cls(
            name="College Standard",
            passing_yards_per_point=20.0,
            reception_points=1.0,
            defense_points_allowed_tiers={
                "0": 10,
                "1-6": 7,
                "7-13": 4,
                "14-20": 1,
                "21-27": 0,
                "28-34": -1,
                "35+": -4,
            },
        )

    @classmethod
    def from_json_file(cls, file_path: str | Path) -> "CfbScoringConfig":
        with open(file_path) as f:
            data = json.load(f)
        base_fields = {
            k: data[k] for k in ScoringConfig.__dataclass_fields__ if k in data and k != "bonus_settings"
        }
        if "bonus_settings" in data:
            base_fields["bonus_settings"] = data["bonus_settings"]
        base = ScoringConfig(**base_fields)
        return cls(
            name=base.name,
            passing_yards_per_point=base.passing_yards_per_point,
            passing_td_points=base.passing_td_points,
            interception_points=base.interception_points,
            passing_2pt_conversion=base.passing_2pt_conversion,
            rushing_yards_per_point=base.rushing_yards_per_point,
            rushing_td_points=base.rushing_td_points,
            rushing_2pt_conversion=base.rushing_2pt_conversion,
            receiving_yards_per_point=base.receiving_yards_per_point,
            receiving_td_points=base.receiving_td_points,
            reception_points=base.reception_points,
            receiving_2pt_conversion=base.receiving_2pt_conversion,
            fumble_lost_points=base.fumble_lost_points,
            fumble_recovered_td=base.fumble_recovered_td,
            bonus_settings=base.bonus_settings,
            field_goal_points=data.get("field_goal_points", 3.0),
            extra_point_points=data.get("extra_point_points", 1.0),
            defense_sack_points=data.get("defense_sack_points", 1.0),
            defense_interception_points=data.get("defense_interception_points", 2.0),
            defense_fumble_recovery_points=data.get("defense_fumble_recovery_points", 2.0),
            defense_td_points=data.get("defense_td_points", 6.0),
            defense_safety_points=data.get("defense_safety_points", 2.0),
            defense_points_allowed_tiers=data.get("defense_points_allowed_tiers", {}),
        )


def _points_allowed_tier(points_allowed: float, tiers: Dict[str, float]) -> float:
    pa = int(points_allowed)
    for label, pts in tiers.items():
        if label == "0" and pa == 0:
            return float(pts)
        if "-" in label:
            lo, hi = label.split("-", 1)
            if lo.isdigit() and hi.isdigit() and int(lo) <= pa <= int(hi):
                return float(pts)
        elif label.endswith("+") and label[:-1].isdigit():
            if pa >= int(label[:-1]):
                return float(pts)
    return 0.0


def calculate_cfb_fantasy_points(
    stats: Dict[str, float],
    config: CfbScoringConfig,
    *,
    opponent_classification: Optional[str] = None,
    fcs_discount: float = 0.75,
    is_dst: bool = False,
) -> float:
    """Compute college fantasy points with optional FCS opponent discount."""
    if is_dst:
        points = (
            stats.get("sacks", 0) * config.defense_sack_points
            + stats.get("interceptions", 0) * config.defense_interception_points
            + stats.get("fumbles_recovered", 0) * config.defense_fumble_recovery_points
            + stats.get("defensive_tds", 0) * config.defense_td_points
            + stats.get("safeties", 0) * config.defense_safety_points
            + _points_allowed_tier(stats.get("points_allowed", 0), config.defense_points_allowed_tiers)
        )
    else:
        points = 0.0
        if config.passing_yards_per_point:
            points += stats.get("passing_yards", 0) / config.passing_yards_per_point
        points += stats.get("passing_tds", 0) * config.passing_td_points
        points += (
            stats.get("passing_interceptions", stats.get("interceptions", 0)) * config.interception_points
        )
        if config.rushing_yards_per_point:
            points += stats.get("rushing_yards", 0) / config.rushing_yards_per_point
        points += stats.get("rushing_tds", 0) * config.rushing_td_points
        if config.receiving_yards_per_point:
            points += stats.get("receiving_yards", 0) / config.receiving_yards_per_point
        points += stats.get("receiving_tds", 0) * config.receiving_td_points
        points += stats.get("receptions", 0) * config.reception_points
        points += stats.get("fumbles_lost", 0) * config.fumble_lost_points
        points += stats.get("field_goals_made", 0) * config.field_goal_points
        points += stats.get("extra_points_made", 0) * config.extra_point_points

    if opponent_classification and opponent_classification.lower() == "fcs" and fcs_discount < 1.0:
        points *= fcs_discount
    return round(points, 2)


def aggregate_player_week_stats(stats_df) -> dict:
    """Sum per-game stat rows into one dict for a player-week."""
    if stats_df.empty:
        return {}
    numeric = [
        "passing_yards",
        "passing_tds",
        "passing_interceptions",
        "passing_completions",
        "passing_attempts",
        "rushing_yards",
        "rushing_tds",
        "rushing_attempts",
        "receiving_yards",
        "receiving_tds",
        "receptions",
        "fumbles_lost",
        "field_goals_made",
        "field_goals_attempts",
        "extra_points_made",
        "extra_points_attempts",
    ]
    out: dict = {}
    for col in numeric:
        if col in stats_df.columns:
            out[col] = float(stats_df[col].sum())
    return out
