#!/usr/bin/env python3
"""End-to-end test of league ingestion against a deployed FFPy web app.

Examples:
  # Use an existing Supabase access token (from browser devtools / localStorage)
  ACCESS_TOKEN=eyJ... uv run python scripts/test_deployed_league_import.py

  # Sign in with email/password against the project's Supabase auth
  SUPABASE_EMAIL=you@example.com SUPABASE_PASSWORD=secret \\
    uv run python scripts/test_deployed_league_import.py

  # Custom target + Sleeper league
  DEPLOYED_URL=https://ffpy-pickem.fly.dev \\
    SLEEPER_LEAGUE_ID=864987755078385664 SEASON=2022 \\
    ACCESS_TOKEN=eyJ... uv run python scripts/test_deployed_league_import.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

DEFAULT_URL = "https://ffpy-pickem.fly.dev"
DEFAULT_LEAGUE = "864987755078385664"  # Sleeper Beginners (LVL 1), public 2022 league
DEFAULT_SEASON = 2022


def _base_url() -> str:
    return os.getenv("DEPLOYED_URL", DEFAULT_URL).rstrip("/")


def _league_prefix() -> str:
    return f"{_base_url()}/league"


def _get_token() -> str:
    token = os.getenv("ACCESS_TOKEN", "").strip()
    if token:
        return token

    email = os.getenv("SUPABASE_EMAIL", "").strip()
    password = os.getenv("SUPABASE_PASSWORD", "").strip()
    if not email or not password:
        print(
            "Set ACCESS_TOKEN or both SUPABASE_EMAIL and SUPABASE_PASSWORD.\n"
            "Tip: sign in at {}/league/, open devtools → Application → Local Storage,\n"
            "and copy the Supabase session access_token.".format(_base_url()),
            file=sys.stderr,
        )
        sys.exit(2)

    config = requests.get(f"{_league_prefix()}/api/auth/config", timeout=30).json()
    supabase_url = (config.get("supabase_url") or "").rstrip("/")
    anon_key = config.get("supabase_anon_key") or ""
    if not supabase_url or not anon_key:
        print("Deployed app did not return Supabase browser auth config.", file=sys.stderr)
        sys.exit(2)

    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Supabase sign-in failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _pretty(data: Any) -> str:
    return json.dumps(data, indent=2)


def main() -> int:
    token = _get_token()
    headers = _auth_headers(token)
    league_id = os.getenv("SLEEPER_LEAGUE_ID", DEFAULT_LEAGUE)
    season = int(os.getenv("SEASON", str(DEFAULT_SEASON)))

    print(f"Target: {_base_url()}")
    print("=== /api/health ===")
    health = requests.get(f"{_base_url()}/api/health", timeout=30).json()
    print(_pretty(health))

    print("=== /league/api/auth/me ===")
    me = requests.get(f"{_league_prefix()}/api/auth/me", headers=headers, timeout=30)
    print(f"HTTP {me.status_code}")
    print(_pretty(me.json()))

    print("=== POST /league/api/leagues/import (sleeper) ===")
    import_resp = requests.post(
        f"{_league_prefix()}/api/leagues/import",
        headers=headers,
        json={"provider": "sleeper", "league_id": league_id, "season": season},
        timeout=120,
    )
    print(f"HTTP {import_resp.status_code}")
    if import_resp.status_code != 200:
        print(import_resp.text, file=sys.stderr)
        return 1
    imported = import_resp.json()
    print(_pretty(imported))
    stored_id = imported["league_id"]

    print("=== GET /league/api/leagues ===")
    leagues = requests.get(f"{_league_prefix()}/api/leagues", headers=headers, timeout=30).json()
    print(_pretty(leagues))

    print(f"=== GET /league/api/leagues/{stored_id}/teams ===")
    teams = requests.get(
        f"{_league_prefix()}/api/leagues/{stored_id}/teams", headers=headers, timeout=30
    ).json()
    print(f"teams={len(teams)}")
    if teams:
        roster = json.loads(teams[0].get("roster_json") or "[]")
        print(f"sample team={teams[0].get('team_name')} roster_players={len(roster)}")

    print(f"=== GET /league/api/leagues/{stored_id}/matchups/1 ===")
    matchups = requests.get(
        f"{_league_prefix()}/api/leagues/{stored_id}/matchups/1", headers=headers, timeout=30
    ).json()
    print(f"week_1_matchups={len(matchups)}")

    print("\nDeployed league ingestion test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
