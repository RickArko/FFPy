"""Sleeper league data fetcher — no auth needed."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from ffpy.integrations.sleeper import SleeperIntegration

logger = logging.getLogger(__name__)


def _load_sleeper_players() -> dict:
    """Load Sleeper player map with caching fallback."""
    from ffpy.draft_strategy import load_sleeper_players

    return load_sleeper_players()


def fetch_sleeper_league(league_id: str, season: int = 2025) -> dict:
    """Fetch league data from Sleeper (public API, no auth required).

    Returns the normalized ``{league, teams, matchups}`` dict used by
    ``ffpy.database.FFPyDatabase.store_user_league()``.
    """
    league = SleeperIntegration.get_league(league_id)
    rosters = SleeperIntegration.get_rosters(league_id)
    users = SleeperIntegration.get_league_users(league_id)
    user_by_id = {u.get("user_id"): u for u in users}
    players_map = _load_sleeper_players()

    teams: List[dict] = []
    for idx, r in enumerate(rosters):
        players_list = r.get("players") or []
        owner_id = r.get("owner_id") or ""
        if not owner_id and not players_list:
            continue
        roster_id = r.get("roster_id")
        user = user_by_id.get(owner_id, {})
        metadata = user.get("metadata") or {}
        fallback_id = str(roster_id) if roster_id is not None else owner_id or str(idx + 1)
        team_name = (
            metadata.get("team_name")
            or user.get("display_name")
            or (f"Team {fallback_id}" if fallback_id else "Unknown")
        )
        owner_display = user.get("display_name") or owner_id or "Unknown"
        team_id_suffix = str(roster_id) if roster_id is not None else owner_id or str(idx + 1)

        teams.append(
            {
                "team_id": f"sleeper:{league_id}:{team_id_suffix}",
                "name": team_name,
                "owner": owner_display,
                "wins": r.get("settings", {}).get("wins", 0),
                "losses": r.get("settings", {}).get("losses", 0),
                "ties": r.get("settings", {}).get("ties", 0),
                "points_for": r.get("settings", {}).get("fpts", 0),
                "points_against": r.get("settings", {}).get("fpts_against", 0),
                "rank": None,
                "roster": SleeperIntegration.enrich_roster(r.get("players", []), players_map),
            }
        )

    teams.sort(key=lambda t: (-(t.get("wins") or 0), -(t.get("points_for") or 0)))
    for idx, team in enumerate(teams, start=1):
        team["rank"] = idx

    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = SleeperIntegration.get_matchups(league_id, week)
        except Exception:
            break
        if not week_matchups:
            break
        by_matchup: dict = defaultdict(list)
        for m in week_matchups:
            matchup_id = m.get("matchup_id")
            roster_id = m.get("roster_id")
            if matchup_id is None or roster_id is None:
                continue
            by_matchup[matchup_id].append(m)
        for group in by_matchup.values():
            if len(group) < 2:
                continue
            home, away = group[0], group[1]
            matchups.append(
                {
                    "week": week,
                    "home_team_id": f"sleeper:{league_id}:{home.get('roster_id')}",
                    "away_team_id": f"sleeper:{league_id}:{away.get('roster_id')}",
                    "home_score": home.get("points"),
                    "away_score": away.get("points"),
                    "is_playoff": 0,
                    "is_consolation": 0,
                }
            )

    return {
        "league": {
            "league_id": f"sleeper:{league_id}",
            "provider": "sleeper",
            "name": league.get("name", "Unknown"),
            "season": league.get("season", season),
            "scoring_type": "custom",
            "roster_size": None,
            "num_teams": len(teams),
            "playoff_teams": league.get("settings", {}).get("playoff_teams"),
        },
        "teams": teams,
        "matchups": matchups,
    }
