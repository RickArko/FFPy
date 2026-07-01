"""Sleeper API — free, no auth needed for read-only public data."""

from __future__ import annotations

import logging
from typing import Any, List

import requests

logger = logging.getLogger(__name__)


class SleeperIntegration:
    """Sleeper API — free, no auth needed."""

    BASE = "https://api.sleeper.app/v1"

    @staticmethod
    def _get(endpoint: str) -> Any:
        url = f"{SleeperIntegration.BASE}{endpoint}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def get_user(username: str) -> dict:
        """GET /v1/user/{username}"""
        return SleeperIntegration._get(f"/user/{username}")

    @staticmethod
    def get_user_leagues(user_id: str, season: int) -> List[dict]:
        """GET /v1/user/{user_id}/leagues/nfl/{season}"""
        return SleeperIntegration._get(f"/user/{user_id}/leagues/nfl/{season}")

    @staticmethod
    def get_league(league_id: str) -> dict:
        """GET /v1/league/{league_id}"""
        return SleeperIntegration._get(f"/league/{league_id}")

    @staticmethod
    def get_rosters(league_id: str) -> List[dict]:
        """GET /v1/league/{league_id}/rosters"""
        return SleeperIntegration._get(f"/league/{league_id}/rosters")

    @staticmethod
    def get_league_users(league_id: str) -> List[dict]:
        """GET /v1/league/{league_id}/users — display names and team metadata."""
        return SleeperIntegration._get(f"/league/{league_id}/users")

    @staticmethod
    def get_matchups(league_id: str, week: int) -> List[dict]:
        """GET /v1/league/{league_id}/matchups/{week}"""
        return SleeperIntegration._get(f"/league/{league_id}/matchups/{week}")

    @staticmethod
    def get_playoff_winners(league_id: str) -> List[dict]:
        """GET /v1/league/{league_id}/winners_bracket"""
        return SleeperIntegration._get(f"/league/{league_id}/winners_bracket")

    @staticmethod
    def get_players() -> dict:
        """GET /v1/players/nfl — full player database (slow, cache it)."""
        return SleeperIntegration._get("/players/nfl")

    @staticmethod
    def player_display_name(player: dict, fallback_id: str = "") -> str:
        """Best-effort display name from a Sleeper player record."""
        if not player:
            return fallback_id or "Unknown"
        name = (player.get("full_name") or "").strip()
        if not name:
            first = (player.get("first_name") or "").strip()
            last = (player.get("last_name") or "").strip()
            name = f"{first} {last}".strip()
        if not name and player.get("position") == "DEF":
            team = player.get("team") or fallback_id
            return f"{team} DST" if team else "DST"
        return name or fallback_id or "Unknown"

    @staticmethod
    def enrich_roster(player_ids: List[Any], players_map: dict) -> List[dict]:
        """Turn Sleeper player IDs into roster dicts with names for storage/UI."""
        enriched: List[dict] = []
        for raw_id in player_ids or []:
            pid = str(raw_id)
            sp = players_map.get(pid, {})
            enriched.append(
                {
                    "player_id": pid,
                    "player": SleeperIntegration.player_display_name(sp, pid),
                    "position": sp.get("position") or "",
                    "team": sp.get("team") or "",
                }
            )
        return enriched
