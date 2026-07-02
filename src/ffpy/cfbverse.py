"""
College football data loader using sportsdataverse / cfbfastR releases.

Downloads parquet assets from GitHub releases (no extra dependencies beyond
polars/pandas already used by FFPy).
"""

from __future__ import annotations

import io
import logging
import sqlite3
import urllib.error
import urllib.request
from typing import Dict, Optional

import pandas as pd
import polars as pl

from ffpy.database import FFPyDatabase

logger = logging.getLogger(__name__)

SPORTSDATAVERSE_BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
USER_AGENT = "FFPy/0.1 (college-football-data-loader)"

ESPN_CFB_POSITIONS: dict[str, str] = {
    "1": "C",
    "2": "CB",
    "3": "DB",
    "4": "DE",
    "5": "DT",
    "6": "FB",
    "7": "FS",
    "8": "G",
    "9": "K",
    "10": "LB",
    "11": "LS",
    "12": "NT",
    "13": "OL",
    "14": "OLB",
    "15": "OT",
    "16": "P",
    "17": "QB",
    "18": "RB",
    "19": "S",
    "20": "SS",
    "21": "T",
    "22": "TE",
    "23": "WR",
    "30": "DL",
    "31": "ATH",
    "32": "PK",
    "35": "OL",
    "37": "DL",
    "45": "WR",
    "78": "DB",
}

# Fallback when GitHub release metadata is unreachable (see espn_cfb_rosters release).
CFB_ROSTER_SEASONS_FALLBACK = frozenset(range(2004, 2023)) | {2024}
CFB_PBP_SEASONS_FALLBACK = frozenset(range(2014, 2026))
CFB_SCHEDULE_SEASONS_FALLBACK = frozenset({2024})


def cfb_pbp_url(season: int) -> str:
    return f"{SPORTSDATAVERSE_BASE}/cfbfastR_cfb_pbp/play_by_play_{season}.parquet"


def cfb_schedule_url(season: int) -> str:
    return f"{SPORTSDATAVERSE_BASE}/espn_cfb_schedules/cfb_schedule_{season}.parquet"


def cfb_roster_urls(season: int) -> list[str]:
    """Return candidate roster parquet URLs (naming varies by release year)."""
    tag = "espn_cfb_rosters"
    return [
        f"{SPORTSDATAVERSE_BASE}/{tag}/rosters_{season}.parquet",
        f"{SPORTSDATAVERSE_BASE}/{tag}/roster_{season}.parquet",
    ]


def get_cfb_roster_seasons() -> frozenset[int]:
    """Return seasons with roster parquet assets on sportsdataverse."""
    import json
    import re

    url = "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_cfb_rosters"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        seasons: set[int] = set()
        for asset in data.get("assets", []):
            match = re.search(r"rosters?_(\d{4})\.parquet", asset.get("name", ""))
            if match:
                seasons.add(int(match.group(1)))
        if seasons:
            return frozenset(seasons)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        pass
    return CFB_ROSTER_SEASONS_FALLBACK


def cfb_roster_availability_message(season: int) -> str | None:
    """Human-readable hint when roster parquet is not published for a season."""
    available = get_cfb_roster_seasons()
    if season in available:
        return None
    latest = max(available) if available else None
    published = ", ".join(str(y) for y in sorted(available))
    return (
        f"No ESPN roster parquet for {season} on sportsdataverse "
        f"(published seasons: {published}). "
        f"Use --skip-rosters to load games/PBP only, or SEASON={latest} for rosters."
    )


def fetch_cfb_parquet(url: str) -> pl.DataFrame:
    """Download a parquet file from a sportsdataverse release URL."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        raise FileNotFoundError(f"CFB data not found at {url}") from exc
    return pl.read_parquet(io.BytesIO(payload))


def _bool_to_int(series: pd.Series) -> pd.Series:
    if series is None:
        return series
    return series.fillna(False).astype(int)


def normalize_cfb_schedule(schedule_df: pd.DataFrame, source: str = "espn") -> pd.DataFrame:
    """Map ESPN schedule parquet columns to cfb_games schema."""
    out = pd.DataFrame()
    out["game_id"] = schedule_df["game_id"].astype(str)
    out["season"] = schedule_df["season"].astype(int)
    out["week"] = schedule_df.get("week")
    out["season_type"] = schedule_df.get("season_type")
    out["game_date"] = schedule_df.get("game_date")
    out["neutral_site"] = _bool_to_int(schedule_df.get("neutral_site"))
    out["conference_game"] = _bool_to_int(schedule_df.get("conference_competition"))
    out["home_id"] = schedule_df.get("home_id")
    out["away_id"] = schedule_df.get("away_id")
    out["home_team"] = schedule_df.get("home_team")
    out["away_team"] = schedule_df.get("away_team")
    out["home_abbreviation"] = schedule_df.get("home_abbreviation")
    out["away_abbreviation"] = schedule_df.get("away_abbreviation")
    out["home_score"] = schedule_df.get("home_score")
    out["away_score"] = schedule_df.get("away_score")
    out["home_winner"] = _bool_to_int(schedule_df.get("home_winner"))
    out["away_winner"] = _bool_to_int(schedule_df.get("away_winner"))
    out["venue"] = schedule_df.get("venue")
    out["attendance"] = schedule_df.get("attendance")
    out["status"] = schedule_df.get("status")
    out["source"] = source

    if "home_score" in out.columns and "away_score" in out.columns:
        finished = schedule_df.get("status")
        if finished is not None:
            out["game_finished"] = finished.eq("STATUS_FINAL").astype(int)
        else:
            out["game_finished"] = (out["home_score"].notna() & out["away_score"].notna()).astype(int)
    else:
        out["game_finished"] = 0

    return out.drop_duplicates(subset=["game_id"]).reset_index(drop=True)


def extract_cfb_games_from_pbp(pbp_df: pd.DataFrame, source: str = "cfbfastR") -> pd.DataFrame:
    """Derive game-level rows from cfbfastR play-by-play when schedule parquet is unavailable."""
    if pbp_df.empty:
        return pd.DataFrame()

    season_col = "year" if "year" in pbp_df.columns else "season"
    grouped = pbp_df.groupby("game_id", sort=False)

    rows: list[dict] = []
    for game_id, game_plays in grouped:
        game_plays = game_plays.sort_values(
            "game_play_number" if "game_play_number" in game_plays else "play_id"
        )
        first = game_plays.iloc[0]
        home = first.get("home")
        away = first.get("away")

        home_score = None
        away_score = None
        if home is not None and pd.notna(home):
            home_mask = game_plays["pos_team"] == home
            if home_mask.any():
                home_score = int(game_plays.loc[home_mask, "pos_team_score"].max())
        if away is not None and pd.notna(away):
            away_mask = game_plays["pos_team"] == away
            if away_mask.any():
                away_score = int(game_plays.loc[away_mask, "pos_team_score"].max())

        rows.append(
            {
                "game_id": str(game_id),
                "season": int(first[season_col]),
                "week": int(first["week"]) if pd.notna(first.get("week")) else None,
                "season_type": None,
                "game_date": None,
                "neutral_site": 0,
                "conference_game": 0,
                "home_id": None,
                "away_id": None,
                "home_team": home,
                "away_team": away,
                "home_abbreviation": None,
                "away_abbreviation": None,
                "home_score": home_score,
                "away_score": away_score,
                "home_winner": int(home_score > away_score)
                if home_score is not None and away_score is not None
                else None,
                "away_winner": int(away_score > home_score)
                if home_score is not None and away_score is not None
                else None,
                "venue": None,
                "attendance": None,
                "status": "STATUS_FINAL" if home_score is not None else None,
                "game_finished": int(home_score is not None and away_score is not None),
                "source": source,
            }
        )

    return pd.DataFrame(rows)


def normalize_cfb_rosters(rosters_df: pd.DataFrame) -> pd.DataFrame:
    """Map ESPN roster parquet columns to cfb_rosters schema."""
    out = pd.DataFrame()
    out["season"] = rosters_df["season"].astype(int)
    out["team_id"] = rosters_df.get("team_id")
    out["athlete_id"] = rosters_df["athlete_id"].astype(int)
    out["athlete_uid"] = rosters_df.get("athlete_uid")
    out["full_name"] = rosters_df.get("full_name")
    out["first_name"] = rosters_df.get("first_name")
    out["last_name"] = rosters_df.get("last_name")

    position_href = rosters_df.get("position_href")
    if position_href is not None:
        out["position_id"] = position_href.astype(str).str.extract(r"/positions/(\d+)", expand=False)
    else:
        out["position_id"] = None

    out["team_abbreviation"] = rosters_df.get("team_abbreviation")
    out["team_name"] = rosters_df.get("team_name")
    out["team_location"] = rosters_df.get("team_location")
    out["jersey"] = rosters_df.get("jersey")
    out["height"] = rosters_df.get("height")
    out["weight"] = rosters_df.get("weight")
    out["age"] = rosters_df.get("age")
    out["date_of_birth"] = rosters_df.get("date_of_birth")
    out["birth_place_city"] = rosters_df.get("birth_place_city")
    out["birth_place_state"] = rosters_df.get("birth_place_state")
    out["experience_years"] = rosters_df.get("experience_years")
    out["experience_display_value"] = rosters_df.get("experience_display_value")
    out["status_name"] = rosters_df.get("status_name")
    out["status_type"] = rosters_df.get("status_type")
    out["headshot_href"] = rosters_df.get("headshot_href")
    out["athlete_href"] = rosters_df.get("athlete_href")
    out["active"] = _bool_to_int(rosters_df.get("active"))

    out = out.dropna(subset=["athlete_id", "full_name"]).reset_index(drop=True)
    return out


def normalize_cfb_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Select and rename cfbfastR PBP columns for cfb_plays storage."""
    season_col = "year" if "year" in pbp_df.columns else "season"
    mapping = {
        "id_play": "play_id",
        "game_id": "game_id",
        season_col: "season",
        "week": "week",
        "play_type": "play_type",
        "play_text": "play_text",
        "period": "period",
        "clock_minutes": "clock_minutes",
        "clock_seconds": "clock_seconds",
        "down": "down",
        "distance": "distance",
        "yards_to_goal": "yards_to_goal",
        "yards_gained": "yards_gained",
        "pos_team": "pos_team",
        "def_pos_team": "def_pos_team",
        "home": "home_team",
        "away": "away_team",
        "passer_player_name": "passer_player_name",
        "rusher_player_name": "rusher_player_name",
        "receiver_player_name": "receiver_player_name",
        "pass": "pass",
        "rush": "rush",
        "rush_td": "rush_td",
        "pass_td": "pass_td",
        "int": "interception",
        "touchdown": "touchdown",
        "EPA": "epa",
        "wpa": "wpa",
        "wp_before": "wp_before",
        "wp_after": "wp_after",
    }

    available = {src: dst for src, dst in mapping.items() if src in pbp_df.columns}
    out = pbp_df[list(available.keys())].rename(columns=available).copy()
    out["play_id"] = out["play_id"].astype(str)
    out["game_id"] = out["game_id"].astype(str)
    out["season"] = out["season"].astype(int)
    return out


def position_from_id(position_id: str | None) -> str | None:
    if position_id is None or (isinstance(position_id, float) and pd.isna(position_id)):
        return None
    return ESPN_CFB_POSITIONS.get(str(position_id))


class CFBVerseLoader:
    """Load college football games, rosters, and play-by-play into FFPy SQLite."""

    def __init__(self, db: Optional[FFPyDatabase] = None):
        self.db = db
        self._own_db = db is None
        if self._own_db:
            self.db = FFPyDatabase()

    def _start_load(self, load_type: str, season: int) -> int | None:
        try:
            return self.db.log_data_load(load_type, season)
        except sqlite3.OperationalError:
            return None

    def _finish_load(
        self,
        load_id: int | None,
        status: str,
        records_loaded: int = 0,
        error: str | None = None,
    ) -> None:
        if load_id is None:
            return
        try:
            self.db.update_data_load(load_id, status, records_loaded, error)
        except sqlite3.OperationalError:
            return

    def __enter__(self) -> "CFBVerseLoader":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._own_db and self.db:
            self.db.close()

    def load_games(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """Load CFB games from ESPN schedule, falling back to PBP extraction."""
        if verbose:
            print(f"Loading CFB games for {season}...")

        load_id = self._start_load("cfb_games", season)
        stored = 0

        try:
            try:
                schedule = fetch_cfb_parquet(cfb_schedule_url(season)).to_pandas()
                games = normalize_cfb_schedule(schedule)
                if verbose:
                    print(f"  [OK] Loaded {len(games)} games from ESPN schedule")
            except FileNotFoundError:
                if verbose:
                    print("  [INFO] Schedule parquet unavailable; extracting games from PBP...")
                pbp = fetch_cfb_parquet(cfb_pbp_url(season)).to_pandas()
                games = extract_cfb_games_from_pbp(pbp)
                if verbose:
                    print(f"  [OK] Extracted {len(games)} games from PBP")

            stored = self.db.store_cfb_games(games)
            self._finish_load(load_id, "completed", stored)
            if verbose:
                print(f"  [OK] Stored {stored} CFB game rows")
        except Exception as exc:
            logger.exception("Failed loading CFB games for %s", season)
            self._finish_load(load_id, "failed", stored, str(exc))
            raise

        return {"stored": stored}

    def load_rosters(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """Load CFB roster data from ESPN rosters release."""
        if verbose:
            print(f"Loading CFB rosters for {season}...")

        unavailable = cfb_roster_availability_message(season)
        if unavailable:
            if verbose:
                print(f"  [WARN] {unavailable}")
            raise FileNotFoundError(unavailable)

        load_id = self._start_load("cfb_rosters", season)
        stored = 0

        try:
            roster_df = None
            last_error: Exception | None = None
            for url in cfb_roster_urls(season):
                try:
                    roster_df = fetch_cfb_parquet(url)
                    if verbose:
                        print(f"  [OK] Fetched rosters from {url.split('/')[-1]}")
                    break
                except FileNotFoundError as exc:
                    last_error = exc

            if roster_df is None:
                message = (
                    cfb_roster_availability_message(season) or f"No CFB roster parquet found for {season}"
                )
                raise FileNotFoundError(message) from last_error

            rosters = normalize_cfb_rosters(roster_df.to_pandas())
            stored = self.db.store_cfb_rosters(rosters, season)
            self._finish_load(load_id, "completed", stored)
            if verbose:
                print(f"  [OK] Stored {stored} CFB roster rows")
        except FileNotFoundError:
            self._finish_load(load_id, "failed", stored, f"rosters unavailable for {season}")
            raise
        except Exception as exc:
            logger.exception("Failed loading CFB rosters for %s", season)
            self._finish_load(load_id, "failed", stored, str(exc))
            raise

        return {"stored": stored}

    def load_pbp(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """Load curated CFB play-by-play for a season."""
        if verbose:
            print(f"Loading CFB play-by-play for {season}...")

        load_id = self._start_load("cfb_pbp", season)
        games_stored = 0
        plays_stored = 0

        try:
            pbp = fetch_cfb_parquet(cfb_pbp_url(season)).to_pandas()
            if verbose:
                print(f"  [OK] Fetched {len(pbp):,} plays")

            # Ensure games exist before plays (FK); merge schedule if available.
            try:
                schedule = fetch_cfb_parquet(cfb_schedule_url(season)).to_pandas()
                games = normalize_cfb_schedule(schedule)
            except FileNotFoundError:
                games = extract_cfb_games_from_pbp(pbp)

            games_stored = self.db.store_cfb_games(games)
            plays = normalize_cfb_plays(pbp)
            plays_stored = self.db.store_cfb_plays(plays, show_progress=verbose)

            self._finish_load(load_id, "completed", plays_stored)
            if verbose:
                print(f"  [OK] Stored {games_stored} games and {plays_stored:,} plays")
        except Exception as exc:
            logger.exception("Failed loading CFB PBP for %s", season)
            self._finish_load(load_id, "failed", plays_stored, str(exc))
            raise

        return {"games": games_stored, "plays": plays_stored}

    def load_season(
        self,
        season: int,
        include_games: bool = True,
        include_rosters: bool = True,
        include_pbp: bool = False,
        verbose: bool = True,
    ) -> Dict[str, int]:
        """Load CFB games, rosters, and optionally PBP for one season."""
        stats = {"games": 0, "rosters": 0, "plays": 0}

        if include_games and not include_pbp:
            stats["games"] = self.load_games(season, verbose=verbose).get("stored", 0)

        if include_rosters:
            try:
                stats["rosters"] = self.load_rosters(season, verbose=verbose).get("stored", 0)
            except FileNotFoundError:
                pass

        if include_pbp:
            pbp_stats = self.load_pbp(season, verbose=verbose)
            stats["games"] = pbp_stats.get("games", stats["games"])
            stats["plays"] = pbp_stats.get("plays", 0)

        return stats
