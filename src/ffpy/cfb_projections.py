"""College football projection model."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase
from ffpy.integrations.cfbd import DEFAULT_CONFERENCES


class CfbProjectionModel:
    """Weighted rolling average of recent CFB fantasy points."""

    def __init__(
        self, db: Optional[FFPyDatabase] = None, lookback_weeks: int = 4, recent_weight: float = 0.6
    ):
        self.db = db or FFPyDatabase()
        self._own_db = db is None
        self.lookback_weeks = lookback_weeks
        self.recent_weight = recent_weight

    def __enter__(self) -> "CfbProjectionModel":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._own_db and self.db:
            self.db.close()

    def generate_projections(
        self,
        season: int,
        week: int,
        conferences: list[str] | None = None,
        model: str = "historical",
    ) -> pd.DataFrame:
        confs = conferences or list(DEFAULT_CONFERENCES)
        players = self.db.get_cfb_players(season=season, conferences=confs, fantasy_eligible=True)
        if players.empty:
            return pd.DataFrame()

        history = self.db.get_cfb_fantasy_points(season=season, max_week=week - 1)
        if history.empty:
            prior = self.db.get_cfb_fantasy_points(season=season - 1)
            if not prior.empty:
                history = prior
            else:
                return pd.DataFrame()

        rows: list[dict] = []
        for _, player in players.iterrows():
            pid = int(player["player_id"])
            ph = (
                history[history["player_id"] == pid]
                .sort_values("week", ascending=False)
                .head(self.lookback_weeks)
            )
            if ph.empty:
                continue
            weights = self._weights(len(ph))
            projected = float(np.average(ph["actual_points"].values, weights=weights))
            stat_cols = [
                "passing_yards",
                "passing_tds",
                "interceptions",
                "rushing_yards",
                "rushing_tds",
                "receiving_yards",
                "receiving_tds",
                "receptions",
            ]
            row = {
                "player_id": pid,
                "season": season,
                "week": week,
                "model": model,
                "projected_points": round(projected, 2),
            }
            for col in stat_cols:
                if col in ph.columns:
                    row[col] = round(float(np.average(ph[col].fillna(0).values, weights=weights)), 2)
            rows.append(row)

        out = pd.DataFrame(rows)
        if not out.empty:
            self.db.store_cfb_projections(out)
        return out

    def _weights(self, n: int) -> np.ndarray:
        if n <= 1:
            return np.ones(n)
        recent = np.linspace(self.recent_weight, 1.0, n)
        recent = recent / recent.sum()
        return recent
