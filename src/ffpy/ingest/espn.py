"""ESPN league data fetcher with public/private auto-detect."""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
import requests

from ffpy.ingest.auth import load_espn_cookies, save_espn_cookies
from ffpy.integrations.espn_league import ESPNLeagueIntegration

logger = logging.getLogger(__name__)


def _prompt_for_cookies() -> tuple[str, str]:
    """Interactively prompt user for ESPN SWID and espn_s2 cookies."""
    print("\n--- ESPN Private League Authentication ---")
    print("Your league appears to be private. Cookies can be found at:")
    print("  Browser DevTools > Application > Cookies > https://www.espn.com\n")
    swid = input("SWID cookie: ").strip()
    s2 = input("espn_s2 cookie: ").strip()
    save = input("Save cookies to ~/.ffpy/espn_cookies.json for reuse? [y/N]: ").strip().lower()
    if save in ("y", "yes"):
        save_espn_cookies(swid, s2)
    return swid, s2


def fetch_espn_league(
    league_id: str,
    season: int = 2025,
    swid: Optional[str] = None,
    espn_s2: Optional[str] = None,
    interactive: bool = True,
) -> dict:
    """Fetch league data from ESPN, trying public access first.

    Returns the normalized ``{league, teams, matchups}`` dict used by
    ``ffpy.database.FFPyDatabase.store_user_league()``.

    * If the league is public, no cookies are needed.
    * If private and cookies are provided via args/env/cookie-file, they are used.
    * If private and no cookies available and ``interactive=True``, prompts the user.
    """
    # Try public first
    integration = ESPNLeagueIntegration(league_id=int(league_id), season=season)
    integration.cookies = {}  # ensure no cookies sent

    public = True
    try:
        info = integration.get_league_info()
        teams = integration.get_all_teams()
        all_rosters = integration.get_all_rosters()
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status not in (401, 403):
            raise
        public = False
        logger.info("League %s requires auth (HTTP %s)", league_id, status)
        info = teams = None
        all_rosters = None

    if not public:
        # Load cookies from args, env, or cookie file
        resolved_swid = swid
        resolved_s2 = espn_s2
        if not resolved_swid or not resolved_s2:
            resolved_swid, resolved_s2 = load_espn_cookies()

        if (not resolved_swid or not resolved_s2) and interactive:
            resolved_swid, resolved_s2 = _prompt_for_cookies()

        if not resolved_swid or not resolved_s2:
            raise RuntimeError(
                f"ESPN league {league_id} is private. "
                "Provide ESPN_SWID and ESPN_S2 via env vars, cookie file, or --swid/--s2 flags."
            )

        integration = ESPNLeagueIntegration(
            league_id=int(league_id), season=season, swid=resolved_swid, espn_s2=resolved_s2
        )
        info = integration.get_league_info()
        teams = integration.get_all_teams()
        all_rosters = integration.get_all_rosters()

    # Build matchups (loop weeks 1-17, stop on failure)
    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = integration.get_matchups(week)
        except Exception:
            break
        for m in week_matchups:
            matchups.append(
                {
                    "week": week,
                    "home_team_id": f"espn:{league_id}:{m['home_team_id']}",
                    "away_team_id": f"espn:{league_id}:{m['away_team_id']}",
                    "home_score": m.get("home_score"),
                    "away_score": m.get("away_score"),
                    "is_playoff": 0,
                    "is_consolation": 0,
                }
            )

    team_list = []
    for t in teams or []:
        tid = t["id"]
        roster = all_rosters.get(tid, pd.DataFrame()) if all_rosters is not None else pd.DataFrame()
        team_list.append(
            {
                "team_id": f"espn:{league_id}:{tid}",
                "name": t["name"],
                "owner": t.get("owner", "Unknown"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": t.get("points_for", 0),
                "points_against": t.get("points_against", 0),
                "rank": t.get("rank"),
                "roster": roster.to_dict(orient="records")
                if isinstance(roster, pd.DataFrame) and not roster.empty
                else [],
            }
        )

    return {
        "league": {
            "league_id": f"espn:{league_id}",
            "provider": "espn",
            "name": (info or {}).get("name", "Unknown"),
            "season": season,
            "scoring_type": ((info or {}).get("scoring_type", "custom") or "custom")
            .lower()
            .replace("-", "_"),
            "roster_size": (info or {}).get("size"),
            "num_teams": len(team_list),
            "playoff_teams": (info or {}).get("playoff_teams"),
        },
        "teams": team_list,
        "matchups": matchups,
    }
