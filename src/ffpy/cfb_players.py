"""Build canonical CFB player registry and ESPN↔CFBD ID crosswalk."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from ffpy.cfbverse import position_from_id
from ffpy.database import FFPyDatabase
from ffpy.integrations.cfbd import DEFAULT_CONFERENCES, FANTASY_POSITIONS, normalize_cfbd_position

FANTASY_POSITIONS_WITH_DST = FANTASY_POSITIONS | {"DST"}


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def build_cfb_players(
    db: FFPyDatabase,
    season: int,
    conferences: list[str] | None = None,
) -> dict[str, int]:
    """Build cfb_players and cfb_id_map from rosters, game stats, and teams."""
    confs = conferences or list(DEFAULT_CONFERENCES)
    conf_set = set(confs)

    teams = db.get_cfb_teams(season=season)
    if teams.empty:
        return {"players": 0, "id_maps": 0}

    eligible_teams = teams[teams["conference"].isin(conf_set)] if "conference" in teams.columns else teams
    team_keys = set(eligible_teams["team_key"].tolist())

    # CFBD athletes from game stats
    stats = db.get_cfb_player_game_stats(season=season)
    roster_df = db.get_cfb_rosters(season=season)

    id_maps: list[dict] = []
    players: list[dict] = []
    seen_cfbd: set[int] = set()

    # From CFBD stats
    if not stats.empty:
        agg: dict = {
            "category": ("category", lambda s: s.mode().iloc[0] if len(s) else ""),
        }
        if "full_name" in stats.columns:
            agg["full_name"] = ("full_name", "first")
        athlete_weeks = stats.groupby(["cfbd_athlete_id", "team_key"]).agg(**agg).reset_index()
        for _, row in athlete_weeks.iterrows():
            cfbd_id = int(row["cfbd_athlete_id"])
            if cfbd_id in seen_cfbd:
                continue
            team_key = row["team_key"]
            if team_key not in team_keys:
                continue
            conf = _team_conference(eligible_teams, team_key)
            pos = _category_to_position(row.get("category", ""))
            display_name = row.get("full_name") if "full_name" in row.index else f"CFBD {cfbd_id}"
            players.append(
                {
                    "season": season,
                    "full_name": display_name or f"CFBD {cfbd_id}",
                    "position": pos,
                    "team_key": team_key,
                    "conference": conf,
                    "cfbd_athlete_id": cfbd_id,
                    "espn_athlete_id": None,
                    "conference_eligible": 1,
                    "fantasy_eligible": int(pos in FANTASY_POSITIONS_WITH_DST if pos else 0),
                }
            )
            seen_cfbd.add(cfbd_id)

    # ESPN roster crosswalk
    if not roster_df.empty:
        roster_df = roster_df.copy()
        if "position_id" in roster_df.columns:
            roster_df["position"] = (
                roster_df["position_id"]
                .astype(str)
                .map(lambda x: position_from_id(x) if pd.notna(x) else None)
            )
        elif "position" not in roster_df.columns:
            roster_df["position"] = None

        for _, r in roster_df.iterrows():
            espn_id = r.get("athlete_id") or r.get("espn_athlete_id")
            if pd.isna(espn_id):
                continue
            espn_id = int(espn_id)
            team_abbr = r.get("team_abbreviation") or ""
            team_key = _match_team_key(eligible_teams, team_abbr, r.get("team_name"))
            if team_key not in team_keys:
                continue
            conf = _team_conference(eligible_teams, team_key)
            pos = r.get("position")
            pos = normalize_cfbd_position(str(pos)) if pos else None
            norm_espn_name = normalize_name(r.get("full_name", ""))

            matched_cfbd = _find_cfbd_match(players, norm_espn_name, team_key)
            if matched_cfbd is not None:
                matched_cfbd["espn_athlete_id"] = espn_id
                id_maps.append(
                    {
                        "season": season,
                        "espn_athlete_id": espn_id,
                        "cfbd_athlete_id": matched_cfbd["cfbd_athlete_id"],
                        "full_name": r.get("full_name"),
                        "team_key": team_key,
                        "match_method": "name_team",
                        "confidence": 0.9,
                    }
                )
            else:
                players.append(
                    {
                        "season": season,
                        "full_name": r.get("full_name"),
                        "position": pos,
                        "team_key": team_key,
                        "conference": conf,
                        "cfbd_athlete_id": None,
                        "espn_athlete_id": espn_id,
                        "conference_eligible": 1,
                        "fantasy_eligible": int(pos in FANTASY_POSITIONS_WITH_DST if pos else 0),
                    }
                )

    stored_players = db.store_cfb_players(pd.DataFrame(players), season)
    stored_maps = db.store_cfb_id_map(pd.DataFrame(id_maps)) if id_maps else 0
    return {"players": stored_players, "id_maps": stored_maps}


def _team_conference(teams: pd.DataFrame, team_key: str) -> str | None:
    row = teams[teams["team_key"] == team_key]
    if row.empty:
        return None
    return row.iloc[0].get("conference")


def _match_team_key(teams: pd.DataFrame, abbrev: str, team_name: str | None) -> str | None:
    if abbrev and "abbreviation" in teams.columns:
        hit = teams[teams["abbreviation"] == abbrev]
        if not hit.empty:
            return hit.iloc[0]["team_key"]
    if team_name and "school" in teams.columns:
        hit = teams[teams["school"].str.lower() == str(team_name).lower()]
        if not hit.empty:
            return hit.iloc[0]["team_key"]
    return None


def _find_cfbd_match(players: list[dict], norm_name: str, team_key: str) -> Optional[dict]:
    for p in players:
        if p.get("team_key") == team_key and normalize_name(p.get("full_name", "")) == norm_name:
            return p
    for p in players:
        if (
            p.get("team_key") == team_key
            and norm_name
            and norm_name in normalize_name(p.get("full_name", ""))
        ):
            return p
    return None


def _category_to_position(category: str) -> str | None:
    cat = (category or "").lower()
    mapping = {
        "passing": "QB",
        "rushing": "RB",
        "receiving": "WR",
        "kicking": "K",
        "puntreturns": "WR",
        "kickreturns": "WR",
        "defensive": "DST",
    }
    return mapping.get(cat)
