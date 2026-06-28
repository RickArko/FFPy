"""Yahoo Fantasy Sports API integration (OAuth 2.0)."""

from __future__ import annotations

import base64
import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class YahooIntegration:
    """Yahoo Fantasy Sports API integration (OAuth 2.0)."""

    AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
    TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
    API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, state: str = "ffpy") -> str:
        """Step 1: redirect user to Yahoo consent page."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
        }
        from urllib.parse import urlencode

        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Step 2: exchange auth code for access + refresh tokens."""
        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        resp = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def refresh_access_token(self, refresh_token: str) -> dict:
        """Step 3: refresh expired access token."""
        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        resp = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get(self, endpoint: str, access_token: str) -> dict:
        """Make an authenticated GET request and return parsed JSON."""
        url = f"{self.API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_user_leagues(self, access_token: str, game_key: str = " nfl") -> List[dict]:
        """GET /users;use_login=1/games;game_keys={game_key}/leagues"""
        # Yahoo game key for NFL changes yearly, e.g., 449 for 2024
        data = self._get(f"/users;use_login=1/games;game_keys={game_key}/leagues", access_token)
        result: List[dict] = []
        try:
            users = data.get("fantasy_content", {}).get("users", {})
            user = users.get("0", {}).get("user", {})
            games = user.get("games", {})
            for key, val in games.items():
                if not isinstance(val, dict):
                    continue
                game = val.get("game", {})
                leagues = game.get("leagues", {})
                for lk, lv in leagues.items():
                    if not isinstance(lv, dict):
                        continue
                    league = lv.get("league", [])
                    if isinstance(league, list) and len(league) > 0:
                        result.append(league[0])
        except Exception as exc:
            logger.warning("Failed to parse Yahoo user leagues: %s", exc)
        return result

    def get_league_metadata(self, league_key: str, access_token: str) -> dict:
        """GET /league/{league_key}/settings"""
        data = self._get(f"/league/{league_key}/settings", access_token)
        try:
            league = data.get("fantasy_content", {}).get("league", [])
            if isinstance(league, list) and len(league) > 0:
                return league[0]
        except Exception as exc:
            logger.warning("Failed to parse Yahoo league metadata: %s", exc)
        return {}

    def get_standings(self, league_key: str, access_token: str) -> List[dict]:
        """GET /league/{league_key}/standings"""
        data = self._get(f"/league/{league_key}/standings", access_token)
        teams: List[dict] = []
        try:
            league = data.get("fantasy_content", {}).get("league", [])
            if isinstance(league, list) and len(league) > 1:
                standings = league[1].get("standings", {})
                for key, val in standings.items():
                    if not isinstance(val, dict):
                        continue
                    team = val.get("team", [])
                    if isinstance(team, list) and len(team) > 0:
                        teams.append(team[0])
        except Exception as exc:
            logger.warning("Failed to parse Yahoo standings: %s", exc)
        return teams

    def get_team_roster(self, team_key: str, access_token: str, week: Optional[int] = None) -> List[dict]:
        """GET /team/{team_key}/roster/players"""
        endpoint = f"/team/{team_key}/roster"
        if week:
            endpoint = f"/team/{team_key}/roster;week={week}"
        data = self._get(endpoint, access_token)
        players: List[dict] = []
        try:
            team = data.get("fantasy_content", {}).get("team", [])
            if isinstance(team, list) and len(team) > 1:
                roster = team[1].get("roster", {})
                for key, val in roster.items():
                    if not isinstance(val, dict):
                        continue
                    player = val.get("player", [])
                    if isinstance(player, list) and len(player) > 0:
                        players.append(player[0])
        except Exception as exc:
            logger.warning("Failed to parse Yahoo roster: %s", exc)
        return players

    def get_matchups(self, league_key: str, week: int, access_token: str) -> List[dict]:
        """GET /league/{league_key}/scoreboard;week={week}"""
        data = self._get(f"/league/{league_key}/scoreboard;week={week}", access_token)
        matchups: List[dict] = []
        try:
            league = data.get("fantasy_content", {}).get("league", [])
            if isinstance(league, list) and len(league) > 1:
                scoreboard = league[1].get("scoreboard", {})
                for key, val in scoreboard.items():
                    if not isinstance(val, dict):
                        continue
                    matchup = val.get("matchup", {})
                    if isinstance(matchup, dict):
                        matchups.append(matchup)
        except Exception as exc:
            logger.warning("Failed to parse Yahoo matchups: %s", exc)
        return matchups
