"""Derive DST (team defense/special teams) weekly fantasy rows.

nflverse player stats have no DST concept — a fantasy DST is the team unit.
This module aggregates per-team defensive/special-teams counting stats from
the raw weekly player stats and joins final scores for points allowed, then
scores each unit week with Sleeper-standard rules (see ``ffpy.scoring``).

Synthetic identity: ``player = "<full team name>"`` (e.g. "San Francisco
49ers"), ``nfl_id = "dst:{ABBR}"`` — matching the Sleeper players map, whose
DEF entries carry the full team name as ``full_name``, so Sleeper roster
entries exact-match these rows.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from ffpy.scoring import score_dst_week

# nflverse team abbreviation for the Rams differs across eras/datasets.
_TEAM_ALIASES = {"LA": "LAR", "STL": "LAR", "OAK": "LV", "SD": "LAC", "WSH": "WAS"}

# Canonical abbreviation → full team name (matches Sleeper's DEF full_name).
_TEAM_NAMES = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LAR": "Los Angeles Rams",
    "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}


def _norm_team(team: object) -> str:
    abbr = str(team or "").strip().upper()
    return _TEAM_ALIASES.get(abbr, abbr)


def _sum_column(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def normalize_games_frame(games: pd.DataFrame) -> pd.DataFrame:
    """Normalize a games/schedule frame to week/teams/scores columns."""
    if games is None or games.empty:
        return pd.DataFrame(columns=["week", "home_team", "away_team", "home_score", "away_score"])
    df = games.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    elif "game_type" in df.columns:
        df = df[df["game_type"] == "REG"]
    out = df[["week", "home_team", "away_team", "home_score", "away_score"]].copy()
    out = out.dropna(subset=["home_score", "away_score"])
    out["home_team"] = out["home_team"].map(_norm_team)
    out["away_team"] = out["away_team"].map(_norm_team)
    out["week"] = out["week"].astype(int)
    out["home_score"] = out["home_score"].astype(int)
    out["away_score"] = out["away_score"].astype(int)
    return out.reset_index(drop=True)


def build_dst_weekly_rows(
    stats_df: pd.DataFrame,
    games_df: pd.DataFrame,
    *,
    season: int,
    start_week: int,
    end_week: int,
    scoring_settings: Optional[dict] = None,
) -> pd.DataFrame:
    """Build one synthetic DST row per team per played week.

    ``stats_df`` is the raw nflverse weekly player frame (all positions —
    defensive columns live on defensive players). ``games_df`` provides final
    scores; team-weeks without a score row are skipped (game not played yet).
    """
    games = normalize_games_frame(games_df)
    if games.empty:
        return pd.DataFrame()
    games = games[(games["week"] >= start_week) & (games["week"] <= end_week)]
    if games.empty:
        return pd.DataFrame()

    stats = pd.DataFrame() if stats_df is None else stats_df.copy()
    if not stats.empty:
        stats = stats[
            (stats["season"] == season)
            & (stats["season_type"] == "REG")
            & (stats["week"].between(start_week, end_week))
        ].copy()
        stats["team"] = stats["team"].map(_norm_team)

    rows = []
    for _, game in games.iterrows():
        week = int(game["week"])
        for team, opponent, points_allowed, home_away in (
            (game["home_team"], game["away_team"], int(game["away_score"]), "home"),
            (game["away_team"], game["home_team"], int(game["home_score"]), "away"),
        ):
            unit = (
                stats[(stats["team"] == team) & (stats["week"] == week)]
                if not stats.empty
                else pd.DataFrame()
            )
            counting = {
                "sacks": _sum_column(unit, "def_sacks"),
                "def_interceptions": _sum_column(unit, "def_interceptions"),
                "fumble_recoveries": _sum_column(unit, "fumble_recovery_opp"),
                "def_tds": _sum_column(unit, "def_tds"),
                "special_teams_tds": _sum_column(unit, "special_teams_tds")
                + _sum_column(unit, "pt_return_tds"),
                "safeties": _sum_column(unit, "def_safeties"),
                "blocked_kicks": _sum_column(unit, "def_punt_blocks")
                + _sum_column(unit, "def_fg_blocks")
                + _sum_column(unit, "def_pat_blocks"),
                "points_allowed": points_allowed,
            }
            rows.append(
                {
                    "player": _TEAM_NAMES.get(team, f"{team} DST"),
                    "team": team,
                    "position": "DST",
                    "opponent": opponent,
                    "home_away": home_away,
                    "week": week,
                    "nfl_id": f"dst:{team}",
                    "actual_points": score_dst_week(counting, scoring_settings),
                    **counting,
                }
            )

    out = pd.DataFrame(rows)
    return out.sort_values(["week", "team"]).reset_index(drop=True)
