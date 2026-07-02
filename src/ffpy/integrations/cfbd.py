"""CollegeFootballData.com API integration for CFB fantasy data."""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import pandas as pd
import requests

from ffpy.config import Config

logger = logging.getLogger(__name__)

CFBD_BASE_URL = "https://api.collegefootballdata.com"
DEFAULT_CONFERENCES = ("SEC", "Big Ten", "ACC")
FANTASY_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "K", "PK"})

# CFBD stat type codes → internal field names
_STAT_MAP = {
    "YDS": {"passing": "passing_yards", "rushing": "rushing_yards", "receiving": "receiving_yards"},
    "TD": {"passing": "passing_tds", "rushing": "rushing_tds", "receiving": "receiving_tds"},
    "INT": {"passing": "passing_interceptions"},
    "ATT": {"passing": "passing_attempts", "rushing": "rushing_attempts"},
    "COMP": {"passing": "passing_completions"},
    "REC": {"receiving": "receptions"},
    "FUM": {"rushing": "fumbles_lost", "receiving": "fumbles_lost"},
    "FGM": {"kicking": "field_goals_made"},
    "FGA": {"kicking": "field_goals_attempts"},
    "XPM": {"kicking": "extra_points_made"},
    "XPA": {"kicking": "extra_points_attempts"},
}


def team_key_from_name(school: str) -> str:
    return school.strip().lower().replace(" ", "_").replace("'", "")


def normalize_cfbd_position(raw: str | None) -> str | None:
    if not raw:
        return None
    pos = raw.upper().strip()
    if pos == "PK":
        return "K"
    return pos


class CFBDClient:
    """Thin client for CollegeFootballData REST API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0, min_interval: float = 0.15):
        self.api_key = api_key or Config.CFBD_API_KEY
        if not self.api_key:
            raise ValueError("CFBD_API_KEY is required. Set it in .env or pass api_key=.")
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        resp = self.session.get(f"{CFBD_BASE_URL}{path}", params=params or {}, timeout=self.timeout)
        self._last_request = time.monotonic()
        resp.raise_for_status()
        return resp.json()

    def fetch_teams(self, season: int, conference: str | None = None) -> pd.DataFrame:
        params: dict[str, Any] = {"year": season}
        if conference:
            params["conference"] = conference
        data = self._get("/teams", params)
        if not data:
            return pd.DataFrame()
        rows = []
        for team in data:
            school = team.get("school") or team.get("name") or ""
            rows.append(
                {
                    "team_key": team_key_from_name(school),
                    "season": season,
                    "cfbd_team": school,
                    "espn_team_id": team.get("id"),
                    "abbreviation": team.get("abbreviation"),
                    "school": school,
                    "conference": team.get("conference") or conference or "",
                    "division": team.get("division"),
                    "classification": team.get("classification"),
                    "color": team.get("color"),
                    "alt_color": team.get("alt_color"),
                }
            )
        return pd.DataFrame(rows)

    def fetch_teams_for_conferences(self, season: int, conferences: list[str] | None = None) -> pd.DataFrame:
        confs = conferences or list(DEFAULT_CONFERENCES)
        frames = [self.fetch_teams(season, conf) for conf in confs]
        frames = [f for f in frames if not f.empty]
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["team_key", "season"])
        return out

    def fetch_games(
        self,
        season: int,
        week: int | None = None,
        conference: str | None = None,
        season_type: str = "regular",
    ) -> pd.DataFrame:
        params: dict[str, Any] = {"year": season, "seasonType": season_type}
        if week is not None:
            params["week"] = week
        if conference:
            params["conference"] = conference
        data = self._get("/games", params)
        if not data:
            return pd.DataFrame()
        rows = []
        for g in data:
            rows.append(
                {
                    "cfbd_game_id": g.get("id"),
                    "season": season,
                    "week": g.get("week"),
                    "season_type": g.get("seasonType"),
                    "game_date": g.get("startDate"),
                    "home_team_key": team_key_from_name(g.get("homeTeam") or ""),
                    "away_team_key": team_key_from_name(g.get("awayTeam") or ""),
                    "home_team": g.get("homeTeam"),
                    "away_team": g.get("awayTeam"),
                    "home_conference": g.get("homeConference"),
                    "away_conference": g.get("awayConference"),
                    "home_classification": g.get("homeClassification"),
                    "away_classification": g.get("awayClassification"),
                    "home_score": g.get("homePoints"),
                    "away_score": g.get("awayPoints"),
                    "neutral_site": int(bool(g.get("neutralSite"))),
                    "conference_game": int(bool(g.get("conferenceGame"))),
                }
            )
        return pd.DataFrame(rows)

    def fetch_game_players(
        self,
        season: int,
        week: int | None = None,
        conference: str | None = None,
        season_type: str = "regular",
    ) -> pd.DataFrame:
        params: dict[str, Any] = {"year": season, "seasonType": season_type}
        if week is not None:
            params["week"] = week
        if conference:
            params["conference"] = conference
        data = self._get("/games/players", params)
        return normalize_cfbd_game_players(data, season, week)

    def fetch_game_teams(
        self,
        season: int,
        week: int | None = None,
        conference: str | None = None,
        season_type: str = "regular",
    ) -> pd.DataFrame:
        params: dict[str, Any] = {"year": season, "seasonType": season_type}
        if week is not None:
            params["week"] = week
        if conference:
            params["conference"] = conference
        data = self._get("/games/teams", params)
        return normalize_cfbd_game_teams(data, season, week)

    def iter_weeks_player_stats(
        self,
        season: int,
        conferences: list[str] | None = None,
        start_week: int = 1,
        end_week: int = 16,
    ) -> Iterator[pd.DataFrame]:
        confs = conferences or list(DEFAULT_CONFERENCES)
        for week in range(start_week, end_week + 1):
            for conf in confs:
                try:
                    df = self.fetch_game_players(season, week=week, conference=conf)
                    if not df.empty:
                        yield df
                except requests.HTTPError as exc:
                    logger.warning(
                        "CFBD game players failed season=%s week=%s conf=%s: %s", season, week, conf, exc
                    )

    def iter_weeks_team_defense(
        self,
        season: int,
        conferences: list[str] | None = None,
        start_week: int = 1,
        end_week: int = 16,
    ) -> Iterator[pd.DataFrame]:
        confs = conferences or list(DEFAULT_CONFERENCES)
        for week in range(start_week, end_week + 1):
            for conf in confs:
                try:
                    df = self.fetch_game_teams(season, week=week, conference=conf)
                    if not df.empty:
                        yield df
                except requests.HTTPError as exc:
                    logger.warning(
                        "CFBD game teams failed season=%s week=%s conf=%s: %s", season, week, conf, exc
                    )


def _apply_cfbd_stat(row: dict[str, Any], cat_name: str, stat_type: str, val: float) -> None:
    """Merge one stat value into a player game row."""
    field = _STAT_MAP.get(stat_type, {}).get(cat_name)
    if field:
        row[field] = row.get(field, 0) + val
        return
    if stat_type == "CAR" and cat_name == "rushing":
        row["rushing_attempts"] = row.get("rushing_attempts", 0) + val


def _parse_catt(stat: str) -> tuple[float | None, float | None]:
    """Parse C/ATT like '16/22' into (completions, attempts)."""
    if "/" not in stat:
        return None, None
    parts = stat.split("/", 1)
    try:
        return float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        return None, None


def normalize_cfbd_game_players(data: list[dict], season: int, week: int | None) -> pd.DataFrame:
    """Flatten CFBD /games/players nested JSON into stat rows."""
    merged: dict[tuple[int, int, str], dict[str, Any]] = {}

    def upsert_row(
        cfbd_game_id: int,
        team_key: str,
        cat_name: str,
        athlete_id: int,
        full_name: str,
    ) -> dict[str, Any]:
        key = (athlete_id, cfbd_game_id, cat_name)
        if key not in merged:
            merged[key] = {
                "cfbd_athlete_id": athlete_id,
                "cfbd_game_id": cfbd_game_id,
                "season": season,
                "week": week,
                "team_key": team_key,
                "category": cat_name,
                "full_name": full_name,
                "source": "cfbd",
            }
        return merged[key]

    for game in data or []:
        cfbd_game_id = game.get("id")
        if cfbd_game_id is None:
            continue
        try:
            cfbd_game_id = int(cfbd_game_id)
        except (TypeError, ValueError):
            continue

        for team_block in game.get("teams") or []:
            team_name = team_block.get("team") or team_block.get("school") or ""
            team_key = team_key_from_name(team_name)
            for category in team_block.get("categories") or []:
                cat_name = (category.get("name") or "").lower()
                types = category.get("types") or []
                category_athletes = category.get("athletes") or []

                # Legacy format: types is list[str], athletes at category level with CSV stats
                if types and isinstance(types[0], str) and category_athletes:
                    for athlete in category_athletes:
                        athlete_id = athlete.get("id")
                        if athlete_id is None:
                            continue
                        try:
                            athlete_id = int(athlete_id)
                        except (TypeError, ValueError):
                            continue
                        if athlete_id < 0:
                            continue
                        full_name = athlete.get("name") or athlete.get("athleteName") or ""
                        if full_name.strip().lower() == "team":
                            continue
                        row = upsert_row(cfbd_game_id, team_key, cat_name, athlete_id, full_name)
                        stat_values = athlete.get("stat") or ""
                        if isinstance(stat_values, str):
                            stat_parts = stat_values.split(",") if stat_values else []
                        elif isinstance(stat_values, list):
                            stat_parts = stat_values
                        else:
                            stat_parts = []
                        for idx, stat_type in enumerate(types):
                            if idx >= len(stat_parts):
                                break
                            try:
                                val = float(stat_parts[idx])
                            except (TypeError, ValueError):
                                if stat_type == "C/ATT":
                                    comp, att = _parse_catt(str(stat_parts[idx]))
                                    if comp is not None:
                                        row["passing_completions"] = row.get("passing_completions", 0) + comp
                                    if att is not None:
                                        row["passing_attempts"] = row.get("passing_attempts", 0) + att
                                continue
                            _apply_cfbd_stat(row, cat_name, stat_type, val)
                    continue

                # Current format: types is list[dict] with per-stat athlete arrays
                for type_block in types:
                    if not isinstance(type_block, dict):
                        continue
                    stat_type = type_block.get("name") or ""
                    for athlete in type_block.get("athletes") or []:
                        athlete_id = athlete.get("id")
                        if athlete_id is None:
                            continue
                        try:
                            athlete_id = int(athlete_id)
                        except (TypeError, ValueError):
                            continue
                        if athlete_id < 0:
                            continue
                        full_name = athlete.get("name") or athlete.get("athleteName") or ""
                        if full_name.strip().lower() == "team":
                            continue
                        row = upsert_row(cfbd_game_id, team_key, cat_name, athlete_id, full_name)
                        stat_raw = athlete.get("stat")
                        if stat_raw is None or stat_raw == "":
                            continue
                        if stat_type == "C/ATT":
                            comp, att = _parse_catt(str(stat_raw))
                            if comp is not None:
                                row["passing_completions"] = row.get("passing_completions", 0) + comp
                            if att is not None:
                                row["passing_attempts"] = row.get("passing_attempts", 0) + att
                            continue
                        try:
                            val = float(stat_raw)
                        except (TypeError, ValueError):
                            continue
                        _apply_cfbd_stat(row, cat_name, stat_type, val)

    if not merged:
        return pd.DataFrame()
    df = pd.DataFrame(list(merged.values()))
    numeric_cols = [
        c
        for c in df.columns
        if c
        not in (
            "cfbd_athlete_id",
            "cfbd_game_id",
            "season",
            "week",
            "team_key",
            "category",
            "full_name",
            "source",
        )
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def normalize_cfbd_game_teams(data: list[dict], season: int, week: int | None) -> pd.DataFrame:
    """Flatten CFBD /games/teams into team defensive stat rows."""
    rows: list[dict] = []
    for game in data or []:
        cfbd_game_id = game.get("id")
        teams = game.get("teams") or []
        team_keys = [team_key_from_name(t.get("team") or t.get("school") or "") for t in teams]
        for i, team_block in enumerate(teams):
            team_name = team_block.get("team") or team_block.get("school") or ""
            team_key = team_key_from_name(team_name)
            opponent_key = team_keys[1 - i] if len(team_keys) == 2 else None
            row: dict[str, Any] = {
                "team_key": team_key,
                "cfbd_game_id": cfbd_game_id,
                "season": season,
                "week": week,
                "opponent_team_key": opponent_key,
                "source": "cfbd",
            }
            for stat in team_block.get("stats") or []:
                category = (stat.get("category") or "").lower()
                stat_type = stat.get("statType") or stat.get("stat") or ""
                try:
                    val = float(stat.get("stat"))
                except (TypeError, ValueError):
                    continue
                if category == "defensive" or stat_type in ("sacks", "interceptions", "fumblesRecovered"):
                    if stat_type == "sacks":
                        row["sacks"] = row.get("sacks", 0) + val
                    elif stat_type == "interceptions":
                        row["interceptions"] = row.get("interceptions", 0) + val
                    elif stat_type in ("fumblesRecovered", "fumbles_recovered"):
                        row["fumbles_recovered"] = row.get("fumbles_recovered", 0) + val
                if stat_type == "points":
                    row["points_allowed"] = val
                if stat_type in ("totalYards", "yards"):
                    row["yards_allowed"] = val
            rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()
