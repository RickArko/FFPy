#!/usr/bin/env python3
"""End-to-end smoke test for the deployed ffpy-sleeper app."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

DEFAULT_URL = "https://ffpy-sleeper.fly.dev"
DEFAULT_SLEEPER_USERNAME = "macker1477"
DEFAULT_LEAGUE = "1312118348556828672"


def _base_url() -> str:
    return os.getenv("DEPLOYED_URL", DEFAULT_URL).rstrip("/")


def _get_token() -> str:
    token = os.getenv("ACCESS_TOKEN", "").strip()
    if token:
        return token

    email = os.getenv("SUPABASE_EMAIL", "").strip()
    password = os.getenv("SUPABASE_PASSWORD", "").strip()
    if not email or not password:
        print(
            "Set ACCESS_TOKEN or both SUPABASE_EMAIL and SUPABASE_PASSWORD.",
            file=sys.stderr,
        )
        sys.exit(2)

    config = requests.get(f"{_base_url()}/api/auth/config", timeout=30).json()
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
    username = os.getenv("SLEEPER_USERNAME", DEFAULT_SLEEPER_USERNAME)

    print(f"Target: {_base_url()}")
    print("=== /api/health ===")
    health = requests.get(f"{_base_url()}/api/health", timeout=30).json()
    print(_pretty(health))
    assert health.get("status") == "ok"

    print("=== PUT /api/profile/sleeper ===")
    profile_resp = requests.put(
        f"{_base_url()}/api/profile/sleeper",
        headers=headers,
        json={"username": username},
        timeout=60,
    )
    print(f"HTTP {profile_resp.status_code}")
    if profile_resp.status_code != 200:
        print(profile_resp.text, file=sys.stderr)
        return 1
    print(_pretty(profile_resp.json()))

    print("=== POST /api/franchises/sync ===")
    sync_resp = requests.post(f"{_base_url()}/api/franchises/sync", headers=headers, timeout=300)
    print(f"HTTP {sync_resp.status_code}")
    if sync_resp.status_code != 200:
        print(sync_resp.text, file=sys.stderr)
        return 1
    franchises = sync_resp.json().get("franchises") or []
    print(f"franchises={len(franchises)}")

    league_id = os.getenv("SLEEPER_LEAGUE_ID", DEFAULT_LEAGUE)
    stored_id = f"sleeper:{league_id}"
    for franchise in franchises:
        for season in franchise.get("seasons") or []:
            if str(season.get("sleeper_league_id")) == league_id:
                stored_id = season["league_id"]
                break

    print(f"=== GET /api/leagues/{stored_id}/teams ===")
    teams = requests.get(
        f"{_base_url()}/api/leagues/{stored_id}/teams",
        headers=headers,
        timeout=120,
    ).json()
    print(f"teams={len(teams)}")
    if not teams:
        print("No teams found for draft-help smoke.", file=sys.stderr)
        return 1
    team_id = teams[0]["team_id"]

    print(f"=== POST /api/leagues/{stored_id}/draft-help ===")
    draft_resp = requests.post(
        f"{_base_url()}/api/leagues/{stored_id}/draft-help",
        headers=headers,
        json={"team_id": team_id, "pick_slots": [1, 20, 21], "num_teams": 10, "num_players": 10},
        timeout=180,
    )
    print(f"HTTP {draft_resp.status_code}")
    if draft_resp.status_code != 200:
        print(draft_resp.text, file=sys.stderr)
        return 1
    draft = draft_resp.json()
    print(f"picks={len(draft.get('picks') or [])} rankings={len(draft.get('rankings') or [])}")

    print("\nDeployed ffpy-sleeper smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
