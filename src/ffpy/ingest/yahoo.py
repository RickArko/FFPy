"""Yahoo league data fetcher with OAuth 2.0 token management."""

from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

from ffpy.ingest.auth import load_yahoo_token, save_yahoo_token
from ffpy.integrations.yahoo import YahooIntegration

logger = logging.getLogger(__name__)


def get_client_credentials() -> tuple[str, str, str]:
    """Load Yahoo client credentials from env vars."""
    client_id = os.getenv("YAHOO_CLIENT_ID", "")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET", "")
    redirect_uri = os.getenv("YAHOO_REDIRECT_URI", "http://127.0.0.1:8001")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Yahoo OAuth requires YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in .env. "
            "Create an app at https://developer.yahoo.com/apps/"
        )
    return client_id, client_secret, redirect_uri


def _ensure_valid_token(
    integration: YahooIntegration,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> dict:
    """Return a valid token dict, refreshing or prompting if needed."""
    # Priority: 1) passed token 2) stored token file 3) interactive prompt
    token = None

    if access_token:
        token = {
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "expires_at": time.time() + 3600,
        }

    if not token:
        token = load_yahoo_token()

    if token:
        now = time.time()
        expires_at = token.get("expires_at", 0)
        if now >= expires_at:
            rt = token.get("refresh_token", "")
            if rt:
                logger.info("Yahoo token expired — refreshing")
                try:
                    new = integration.refresh_access_token(rt)
                    new["expires_at"] = time.time() + new.get("expires_in", 3600)
                    save_yahoo_token(new)
                    return new
                except Exception as exc:
                    logger.warning("Token refresh failed: %s", exc)
            logger.warning("Token expired and no refresh token available")
            token = None

    if not token:
        # Interactive OAuth flow
        print("\n--- Yahoo OAuth 2.0 Authentication ---")
        auth_url = integration.get_authorization_url(state="ffpy-ingest")
        print(f"1. Visit this URL in your browser:\n   {auth_url}")
        print("2. Authorize the application")
        print("3. Copy the full redirect URL and paste it below\n")
        redirect_response = input("Paste redirect URL or authorization code: ").strip()

        # Extract code from URL if full URL pasted
        if "code=" in redirect_response:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(redirect_response)
            params = parse_qs(parsed.query)
            code = params.get("code", [""])[0]
        else:
            code = redirect_response

        if not code:
            raise RuntimeError("No authorization code provided")

        token = integration.exchange_code(code)
        token["expires_at"] = time.time() + token.get("expires_in", 3600)
        save_yahoo_token(token)

    return token


def fetch_yahoo_league(
    league_id: str,
    season: int = 2025,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> dict:
    """Fetch league data from Yahoo Fantasy Sports via OAuth 2.0.

    Returns the normalized ``{league, teams, matchups}`` dict.
    """
    client_id, client_secret, redirect_uri = get_client_credentials()
    integration = YahooIntegration(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    token = _ensure_valid_token(integration, access_token, refresh_token)
    token_str = token["access_token"]

    meta = integration.get_league_metadata(league_id, token_str)
    standings = integration.get_standings(league_id, token_str)

    teams = []
    for s in standings:
        team_key = s.get("team_key", "")
        roster = integration.get_team_roster(team_key, token_str) if team_key else []
        teams.append(
            {
                "team_id": f"yahoo:{league_id}:{team_key}",
                "name": s.get("name", "Unknown"),
                "owner": s.get("manager", {}).get("nickname", "Unknown"),
                "wins": s.get("standings", {}).get("outcome_totals", {}).get("wins", 0),
                "losses": s.get("standings", {}).get("outcome_totals", {}).get("losses", 0),
                "ties": s.get("standings", {}).get("outcome_totals", {}).get("ties", 0),
                "points_for": s.get("standings", {}).get("points_for", 0),
                "points_against": s.get("standings", {}).get("points_against", 0),
                "rank": s.get("standings", {}).get("rank"),
                "roster": roster if isinstance(roster, list) else [],
            }
        )

    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = integration.get_matchups(league_id, week, token_str)
        except Exception:
            break
        for m in week_matchups:
            teams_in = m.get("teams", {})
            home = away = None
            for key, val in teams_in.items():
                if not isinstance(val, dict):
                    continue
                t = val.get("team", [])
                if isinstance(t, list) and len(t) > 1:
                    tk = t[0].get("team_key", "")
                    if home is None:
                        home = tk
                    else:
                        away = tk
            if home and away:
                matchups.append(
                    {
                        "week": week,
                        "home_team_id": f"yahoo:{league_id}:{home}",
                        "away_team_id": f"yahoo:{league_id}:{away}",
                        "home_score": None,
                        "away_score": None,
                        "is_playoff": 0,
                        "is_consolation": 0,
                    }
                )

    return {
        "league": {
            "league_id": f"yahoo:{league_id}",
            "provider": "yahoo",
            "name": meta.get("name", "Unknown"),
            "season": season,
            "scoring_type": "custom",
            "roster_size": None,
            "num_teams": meta.get("num_teams"),
            "playoff_teams": None,
        },
        "teams": teams,
        "matchups": matchups,
    }
