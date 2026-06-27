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
