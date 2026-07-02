"""College football projection model."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase
from ffpy.integrations.cfbd import DEFAULT_CONFERENCES, team_key_from_name

STAT_COLS = [
    "passing_yards",
    "passing_tds",
    "interceptions",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "receptions",
]


class CfbProjectionModel:
    """Weighted rolling average of recent CFB fantasy points with optional opponent adjustment."""

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

        current_history = self.db.get_cfb_fantasy_points(season=season, max_week=week - 1)
        prior_history = self.db.get_cfb_fantasy_points(season=season - 1)
        if current_history.empty and prior_history.empty:
            return pd.DataFrame()

        pos_conf_means = self._position_conference_means(current_history, prior_history, season)
        defense_factors = self._defense_adjustment_factors(season, confs) if model == "opponent_adj" else {}
        schedule = self._week_schedule_opponents(season, week) if model == "opponent_adj" else {}

        rows: list[dict] = []
        for _, player in players.iterrows():
            pid = int(player["player_id"])
            projected, stat_avgs = self._project_player(
                pid=pid,
                player=player,
                season=season,
                week=week,
                current_history=current_history,
                prior_history=prior_history,
                pos_conf_means=pos_conf_means,
            )
            if projected is None:
                continue

            if model == "opponent_adj":
                team_key = player.get("team_key") or ""
                opp_key = schedule.get(team_key)
                if opp_key and opp_key in defense_factors:
                    projected = round(projected * defense_factors[opp_key], 2)
                    stat_avgs = {k: round(v * defense_factors[opp_key], 2) for k, v in stat_avgs.items()}

            row = {
                "player_id": pid,
                "season": season,
                "week": week,
                "model": model,
                "projected_points": projected,
            }
            row.update(stat_avgs)
            rows.append(row)

        out = pd.DataFrame(rows)
        if not out.empty:
            self.db.store_cfb_projections(out)
        return out

    def _project_player(
        self,
        pid: int,
        player: pd.Series,
        season: int,
        week: int,
        current_history: pd.DataFrame,
        prior_history: pd.DataFrame,
        pos_conf_means: dict[tuple[str, str], float],
    ) -> tuple[Optional[float], dict[str, float]]:
        ph = (
            current_history[current_history["player_id"] == pid]
            .sort_values("week", ascending=False)
            .head(self.lookback_weeks)
        )
        if not ph.empty:
            weights = self._weights(len(ph))
            projected = float(np.average(ph["actual_points"].values, weights=weights))
            stat_avgs = self._weighted_stat_avgs(ph, weights)
            return round(projected, 2), stat_avgs

        # Week 1 / no current-season games: blend prior-season player avg + position/conference mean
        prior_player = prior_history[prior_history["player_id"] == pid]
        position = str(player.get("position") or "")
        conference = str(player.get("conference") or "")
        pos_mean = pos_conf_means.get((position, conference), 0.0)

        if prior_player.empty:
            if pos_mean <= 0:
                return None, {}
            return round(pos_mean, 2), {}

        prior_avg = float(prior_player["actual_points"].mean())
        if pos_mean > 0:
            projected = 0.7 * prior_avg + 0.3 * pos_mean
        else:
            projected = prior_avg
        weights = self._weights(min(len(prior_player), self.lookback_weeks))
        stat_avgs = self._weighted_stat_avgs(
            prior_player.sort_values("week", ascending=False).head(self.lookback_weeks), weights
        )
        return round(projected, 2), stat_avgs

    def _weighted_stat_avgs(self, ph: pd.DataFrame, weights: np.ndarray) -> dict[str, float]:
        stat_avgs: dict[str, float] = {}
        for col in STAT_COLS:
            if col in ph.columns:
                stat_avgs[col] = round(float(np.average(ph[col].fillna(0).values, weights=weights)), 2)
        return stat_avgs

    def _position_conference_means(
        self,
        current_history: pd.DataFrame,
        prior_history: pd.DataFrame,
        season: int,
    ) -> dict[tuple[str, str], float]:
        players = self.db.get_cfb_players(season=season, fantasy_eligible=True)
        if players.empty:
            return {}
        history = current_history if not current_history.empty else prior_history
        if history.empty:
            return {}
        merged = history.merge(players[["player_id", "position", "conference"]], on="player_id", how="inner")
        if merged.empty:
            return {}
        grouped = merged.groupby(["position", "conference"])["actual_points"].mean()
        return {(str(k[0]), str(k[1])): float(v) for k, v in grouped.items()}

    def _defense_adjustment_factors(self, season: int, conferences: list[str]) -> dict[str, float]:
        def_stats = self.db.get_cfb_team_defense_stats(season=season)
        teams = self.db.get_cfb_teams(season=season)
        if def_stats.empty or teams.empty:
            return {}
        eligible = teams[teams["conference"].isin(conferences)] if "conference" in teams.columns else teams
        eligible_keys = set(eligible["team_key"].tolist())
        filtered = def_stats[def_stats["team_key"].isin(eligible_keys)]
        if filtered.empty or "points_allowed" not in filtered.columns:
            return {}
        avg_pa = float(filtered["points_allowed"].mean())
        if avg_pa <= 0:
            return {}
        factors: dict[str, float] = {}
        for team_key, grp in filtered.groupby("team_key"):
            team_pa = float(grp["points_allowed"].mean())
            raw = 1.0 + (team_pa - avg_pa) / avg_pa * 0.1
            factors[str(team_key)] = max(0.85, min(1.15, raw))
        return factors

    def _week_schedule_opponents(self, season: int, week: int) -> dict[str, str]:
        games = pd.read_sql(
            "SELECT week, home_team, away_team FROM cfb_games WHERE season = ? AND week = ?",
            self.db.conn,
            params=[season, week],
        )
        teams = self.db.get_cfb_teams(season=season)
        if games.empty or teams.empty:
            return {}
        school_to_key = {str(r["school"]): str(r["team_key"]) for _, r in teams.iterrows()}
        abbr_to_key = {
            str(r["abbreviation"]): str(r["team_key"]) for _, r in teams.iterrows() if r.get("abbreviation")
        }

        def resolve(name: str) -> Optional[str]:
            if not name:
                return None
            if name in school_to_key:
                return school_to_key[name]
            if name in abbr_to_key:
                return abbr_to_key[name]
            key = team_key_from_name(name)
            return key if key in set(teams["team_key"]) else None

        schedule: dict[str, str] = {}
        for _, g in games.iterrows():
            home_key = resolve(str(g.get("home_team") or ""))
            away_key = resolve(str(g.get("away_team") or ""))
            if home_key and away_key:
                schedule[home_key] = away_key
                schedule[away_key] = home_key
        return schedule

    def _weights(self, n: int) -> np.ndarray:
        if n <= 1:
            return np.ones(n)
        recent = np.linspace(self.recent_weight, 1.0, n)
        return recent / recent.sum()
