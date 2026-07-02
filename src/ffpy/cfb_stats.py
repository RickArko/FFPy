"""Compute CFB fantasy points from player game stats and team defense stats."""

from __future__ import annotations

import pandas as pd

from ffpy.cfb_scoring import CfbScoringConfig, aggregate_player_week_stats, calculate_cfb_fantasy_points
from ffpy.database import FFPyDatabase
from ffpy.integrations.cfbd import DEFAULT_CONFERENCES


def compute_cfb_fantasy_points(
    db: FFPyDatabase,
    season: int,
    scoring_preset: str = "college_standard",
    fcs_discount: float = 0.75,
    conferences: list[str] | None = None,
) -> int:
    """Aggregate game stats to weekly fantasy points and store in cfb_fantasy_points."""
    config = CfbScoringConfig.college_standard()
    confs = conferences or list(DEFAULT_CONFERENCES)

    stats = db.get_cfb_player_game_stats(season=season)
    players = db.get_cfb_players(season=season, conferences=confs)
    if stats.empty or players.empty:
        return 0

    stats = stats.merge(
        players[["player_id", "cfbd_athlete_id", "conference", "conference_eligible", "position"]],
        on="cfbd_athlete_id",
        how="inner",
    )

    games = db.get_cfb_game_meta(season=season)
    opp_class = {}
    if not games.empty and "cfbd_game_id" in games.columns:
        for _, g in games.iterrows():
            gid = g.get("cfbd_game_id")
            if gid is not None:
                opp_class[int(gid)] = {
                    "home_class": g.get("home_classification"),
                    "away_class": g.get("away_classification"),
                    "home_key": g.get("home_team_key"),
                    "away_key": g.get("away_team_key"),
                }

    rows: list[dict] = []
    grouped = stats.groupby(["player_id", "season", "week", "team_key"])
    for (player_id, yr, week, team_key), grp in grouped:
        agg = aggregate_player_week_stats(grp)
        opp_classification = None
        fcs_applied = 0
        if not grp.empty and "cfbd_game_id" in grp.columns:
            gid = int(grp["cfbd_game_id"].iloc[0])
            meta = opp_class.get(gid, {})
            if team_key == meta.get("home_key"):
                opp_classification = meta.get("away_class")
            elif team_key == meta.get("away_key"):
                opp_classification = meta.get("home_class")
            if opp_classification and str(opp_classification).lower() == "fcs":
                fcs_applied = 1

        position = grp["position"].iloc[0] if "position" in grp.columns else None
        points = calculate_cfb_fantasy_points(
            agg,
            config,
            opponent_classification=opp_classification,
            fcs_discount=fcs_discount,
            is_dst=position == "DST",
        )
        rows.append(
            {
                "player_id": int(player_id),
                "season": int(yr),
                "week": int(week) if pd.notna(week) else 0,
                "scoring_preset": scoring_preset,
                "actual_points": points,
                "passing_yards": agg.get("passing_yards", 0),
                "passing_tds": agg.get("passing_tds", 0),
                "interceptions": agg.get("passing_interceptions", 0),
                "rushing_yards": agg.get("rushing_yards", 0),
                "rushing_tds": agg.get("rushing_tds", 0),
                "receiving_yards": agg.get("receiving_yards", 0),
                "receiving_tds": agg.get("receiving_tds", 0),
                "receptions": agg.get("receptions", 0),
                "fumbles_lost": agg.get("fumbles_lost", 0),
                "field_goals_made": agg.get("field_goals_made", 0),
                "extra_points_made": agg.get("extra_points_made", 0),
                "opponent_classification": opp_classification,
                "fcs_discount_applied": fcs_applied,
                "conference_eligible": int(grp["conference_eligible"].iloc[0])
                if "conference_eligible" in grp.columns
                else 1,
                "team_key": team_key,
                "opponent_team_key": grp["opponent_team_key"].iloc[0]
                if "opponent_team_key" in grp.columns
                else None,
            }
        )

    # DST rows from team defense stats
    def_stats = db.get_cfb_team_defense_stats(season=season)
    dst_players = players[players["position"] == "DST"]
    if not def_stats.empty and not dst_players.empty:
        for _, ds in def_stats.iterrows():
            dst = dst_players[dst_players["team_key"] == ds["team_key"]]
            if dst.empty:
                continue
            player_id = int(dst.iloc[0]["player_id"])
            dst_agg = {
                "sacks": ds.get("sacks", 0),
                "interceptions": ds.get("interceptions", 0),
                "fumbles_recovered": ds.get("fumbles_recovered", 0),
                "defensive_tds": ds.get("defensive_tds", 0),
                "safeties": ds.get("safeties", 0),
                "points_allowed": ds.get("points_allowed", 0),
            }
            points = calculate_cfb_fantasy_points(dst_agg, config, is_dst=True)
            rows.append(
                {
                    "player_id": player_id,
                    "season": int(ds["season"]),
                    "week": int(ds["week"]) if pd.notna(ds.get("week")) else 0,
                    "scoring_preset": scoring_preset,
                    "actual_points": points,
                    "conference_eligible": 1,
                    "team_key": ds["team_key"],
                    "opponent_team_key": ds.get("opponent_team_key"),
                    "fcs_discount_applied": 0,
                }
            )

    if not rows:
        return 0
    return db.store_cfb_fantasy_points(pd.DataFrame(rows))
