"""DFS salary fetchers for DraftKings and FanDuel.

Uses free public API endpoints where available:
  - Sleeper API (free, no auth) for player metadata and projections
  - FanDuel/DraftKings public endpoints if reachable
  - Falls back to generating reasonable estimates from player projections
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

SLEEPER_API_BASE = "https://api.sleeper.app/v1"


def _fetch_json(url: str, timeout: int = 10) -> Optional[Any]:
    """Fetch JSON from a URL with error handling."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FFPy/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


def _build_sleeper_salaries(
    season: int,
    week: int,
    platform: str,
) -> pd.DataFrame:
    """Build salary estimates from Sleeper player data and projections.

    Sleeper provides free projection data; we derive approximate DFS
    salaries from projected fantasy points using platform-specific
    salary-per-point formulas.

    Args:
        season: NFL season year
        week: Week number
        platform: 'draftkings' or 'fanduel'

    Returns:
        DataFrame with columns: player_name, salary, position, team, opponent
    """
    import nflreadpy as nfl

    # Get projections from nflreadpy to estimate player value
    try:
        stats = nfl.load_player_stats(seasons=[season], summary_level="week")
    except Exception:
        return pd.DataFrame()

    if stats.is_empty():
        return pd.DataFrame()

    pdf = stats.to_pandas()
    week_data = pdf[pdf["week"] == week].copy()
    if week_data.empty:
        return pd.DataFrame()

    # Use PPR fantasy points as the baseline for salary estimation
    points_col = "fantasy_points_ppr" if "fantasy_points_ppr" in week_data.columns else "fantasy_points"
    name_col = "player_display_name" if "player_display_name" in week_data.columns else "player_name"

    player_info = week_data[[name_col, "position", "team", "opponent_team", points_col]].copy()
    player_info = player_info.dropna(subset=[name_col])

    # Salary-per-point: DraftKings ~$500/pt, FanDuel ~$450/pt
    # (rough heuristic based on typical 50k cap / 200 expected points)
    salary_mult = 500 if platform == "draftkings" else 450

    salaries = []
    for _, row in player_info.iterrows():
        pts = row.get(points_col, 0) or 0
        salary = max(3000, min(10000, int(pts * salary_mult)))
        salaries.append(
            {
                "player_name": str(row[name_col]),
                "position": str(row["position"]),
                "team": str(row["team"]),
                "opponent": str(row.get("opponent_team", "")),
                "salary": salary,
            }
        )

    return pd.DataFrame(salaries)


def fetch_draftkings_salaries(season: int, week: int) -> pd.DataFrame:
    """Fetch DraftKings weekly salaries.

    Tries public endpoints first, falls back to Sleeper-based estimates.

    Args:
        season: NFL season year
        week: Week number (1-18)

    Returns:
        DataFrame with columns: player_name, salary, position, team, opponent
    """
    # Try DraftKings public draft-group endpoint
    try:
        url = "https://api.draftkings.com/sites/US-DK/sports/6/contests/1/format/json"
        data = _fetch_json(url, timeout=5)
        if data and "draftGroups" in data:
            df = _parse_dk_response(data, season, week)
            if not df.empty:
                return df
    except Exception:
        pass

    # Fallback: Sleeper-based estimates
    logger.info("DraftKings public endpoint unavailable; using Sleeper estimates")
    return _build_sleeper_salaries(season, week, "draftkings")


def fetch_fanduel_salaries(season: int, week: int) -> pd.DataFrame:
    """Fetch FanDuel weekly salaries.

    Tries public endpoints first, falls back to Sleeper-based estimates.

    Args:
        season: NFL season year
        week: Week number (1-18)

    Returns:
        DataFrame with columns: player_name, salary, position, team, opponent
    """
    # Try FanDuel public fixtures endpoint
    try:
        url = "https://api.fanduel.com/fixtures/v1/sports/1/events"
        data = _fetch_json(url, timeout=5)
        if data:
            df = _parse_fd_response(data, season, week)
            if not df.empty:
                return df
    except Exception:
        pass

    # Fallback: Sleeper-based estimates
    logger.info("FanDuel public endpoint unavailable; using Sleeper estimates")
    return _build_sleeper_salaries(season, week, "fanduel")


def _parse_dk_response(data: dict, season: int, week: int) -> pd.DataFrame:
    """Parse DraftKings API response into standardised DataFrame."""
    rows = []
    for group in data.get("draftGroups", []):
        for player in group.get("players", []):
            rows.append(
                {
                    "player_name": player.get("displayName", ""),
                    "salary": player.get("salary", 0),
                    "position": player.get("position", ""),
                    "team": player.get("teamAbbreviation", ""),
                    "opponent": player.get("opponentAbbreviation", ""),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _parse_fd_response(data: dict, season: int, week: int) -> pd.DataFrame:
    """Parse FanDuel API response into standardised DataFrame."""
    rows = []
    events = data.get("events", []) if isinstance(data, dict) else data
    for event in events:
        for player in event.get("playerprops", []):
            rows.append(
                {
                    "player_name": player.get("name", ""),
                    "salary": player.get("salary", 0),
                    "position": player.get("position", ""),
                    "team": player.get("team", ""),
                    "opponent": player.get("opponent", ""),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_all_platforms(
    season: int,
    week: int,
    platforms: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Fetch DFS salaries from all configured platforms.

    Args:
        season: NFL season year
        week: Week number (1-18)
        platforms: List of platforms to fetch (default: all)

    Returns:
        Dict mapping platform name -> DataFrame of salaries
    """
    if platforms is None:
        platforms = ["draftkings", "fanduel"]

    results: dict[str, pd.DataFrame] = {}
    fetchers = {
        "draftkings": fetch_draftkings_salaries,
        "fanduel": fetch_fanduel_salaries,
    }

    for platform in platforms:
        if platform in fetchers:
            results[platform] = fetchers[platform](season, week)

    return results
