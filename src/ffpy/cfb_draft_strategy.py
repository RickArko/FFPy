"""CFB draft strategy engine — ADP value, positional need, VORP from projections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from ffpy.database import FFPyDatabase

DRAFTABLE_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"]
DEFAULT_STARTER_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DST": 1}


@dataclass
class CfbDraftStrategyConfig:
    weight_need: float = 0.35
    weight_adp_value: float = 0.25
    weight_vorp: float = 0.40
    model: str = "historical"
    week: int = 1
    starter_slots: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_STARTER_SLOTS))


class CfbDraftStrategyEngine:
    """Rank draft targets for a CFB league team."""

    def __init__(self, db: FFPyDatabase, config: Optional[CfbDraftStrategyConfig] = None):
        self.db = db
        self.config = config or CfbDraftStrategyConfig()

    def _replacement_levels(self, projections: pd.DataFrame) -> dict[str, float]:
        levels: dict[str, float] = {}
        for pos in DRAFTABLE_POSITIONS:
            pos_df = projections[projections["position"] == pos]
            if pos_df.empty:
                levels[pos] = 0.0
                continue
            slot = self.config.starter_slots.get(pos, 1)
            if pos == "FLEX":
                continue
            n = max(1, slot * 12)
            sorted_pts = pos_df["projected_points"].sort_values(ascending=False)
            levels[pos] = float(sorted_pts.iloc[min(n - 1, len(sorted_pts) - 1)])
        return levels

    def _roster_needs(self, roster: pd.DataFrame) -> dict[str, float]:
        counts: dict[str, int] = {p: 0 for p in DRAFTABLE_POSITIONS}
        for _, row in roster.iterrows():
            pos = row.get("position") or "FLEX"
            if pos in counts:
                counts[pos] += 1
        needs: dict[str, float] = {}
        for pos, target in self.config.starter_slots.items():
            if pos == "FLEX":
                continue
            gap = max(0, target - counts.get(pos, 0))
            needs[pos] = gap / max(target, 1)
        return needs

    def generate(
        self,
        league_id: str,
        team_id: str,
        num_players: int = 50,
    ) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        season = int(league["season"])
        confs = json.loads(league.get("allowed_conferences") or "[]")

        projections = self.db.get_cfb_projections(
            season=season,
            week=self.config.week,
            model=self.config.model,
            conferences=confs,
        )
        if projections.empty:
            raise ValueError("No projections available")

        adp = self.db.get_cfb_adp(season=season)
        adp_map = {}
        if not adp.empty:
            adp_map = {int(r["player_id"]): int(r["rank"]) for _, r in adp.iterrows()}

        rostered = self.db.get_cfb_league_rostered_player_ids(league_id)
        roster = self.db.get_cfb_league_roster(team_id)
        needs = self._roster_needs(roster)
        replacement = self._replacement_levels(projections)

        candidates = projections[~projections["player_id"].isin(rostered)].copy()
        if candidates.empty:
            return {"recommendations": [], "team_id": team_id}

        rows: list[dict] = []
        for _, row in candidates.iterrows():
            pid = int(row["player_id"])
            pos = row.get("position") or "FLEX"
            proj = float(row.get("projected_points") or 0)
            rep = replacement.get(pos, 0.0)
            vorp = proj - rep
            need = needs.get(pos, 0.0)
            adp_rank = adp_map.get(pid, 999)
            adp_value = max(0, (200 - adp_rank) / 200.0)

            score = (
                self.config.weight_need * need
                + self.config.weight_adp_value * adp_value
                + self.config.weight_vorp * (vorp / 20.0 if vorp else 0)
            )
            reasons = []
            if need > 0.3:
                reasons.append(f"Need at {pos}")
            if vorp > 5:
                reasons.append(f"VORP +{vorp:.1f}")
            if adp_rank < 50:
                reasons.append(f"ADP #{adp_rank}")

            rows.append(
                {
                    "player_id": pid,
                    "full_name": row.get("full_name"),
                    "position": pos,
                    "team_key": row.get("team_key"),
                    "projected_points": round(proj, 2),
                    "vorp": round(vorp, 2),
                    "adp_rank": adp_rank if pid in adp_map else None,
                    "score": round(score, 4),
                    "reasons": reasons or ["Best available"],
                }
            )

        rows.sort(key=lambda x: -x["score"])
        return {
            "league_id": league_id,
            "team_id": team_id,
            "season": season,
            "model": self.config.model,
            "recommendations": rows[:num_players],
        }

    def player_outlook(self, player_id: int, season: int, week: int = 1) -> dict[str, Any]:
        player = self.db.get_cfb_players(season=season)
        match = player[player["player_id"] == player_id]
        if match.empty:
            raise ValueError("Player not found")
        row = match.iloc[0]
        proj = self.db.get_cfb_projections(season=season, week=week, model=self.config.model)
        player_proj = proj[proj["player_id"] == player_id]
        pts = float(player_proj.iloc[0]["projected_points"]) if not player_proj.empty else 0.0
        adp = self.db.get_cfb_adp(season=season)
        adp_row = adp[adp["player_id"] == player_id] if not adp.empty else pd.DataFrame()
        return {
            "player_id": player_id,
            "full_name": row["full_name"],
            "position": row["position"],
            "team_key": row["team_key"],
            "conference": row.get("conference"),
            "season": season,
            "week": week,
            "projected_points": pts,
            "adp_rank": int(adp_row.iloc[0]["rank"]) if not adp_row.empty else None,
        }


def compute_cfb_adp_from_projections(
    db: FFPyDatabase,
    season: int,
    week: int | None = None,
    model: str = "historical",
    conferences: Optional[list[str]] = None,
) -> int:
    """Rank players by projected points and store as ADP."""
    from ffpy.integrations.cfbd import DEFAULT_CONFERENCES

    confs = conferences or list(DEFAULT_CONFERENCES)
    if week is None:
        row = db.conn.execute(
            """
            SELECT MIN(week) FROM cfb_projections
            WHERE season = ? AND model = ?
            """,
            (season, model),
        ).fetchone()
        week = int(row[0]) if row and row[0] is not None else 1
    proj = db.get_cfb_projections(season=season, week=week, model=model, conferences=confs)
    if proj.empty:
        return 0
    ranked = proj.sort_values("projected_points", ascending=False).reset_index(drop=True)
    rows = []
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        rows.append(
            {
                "season": season,
                "player_id": int(row["player_id"]),
                "rank": rank,
                "source": "projections",
            }
        )
    return db.store_cfb_adp(pd.DataFrame(rows))
