"""Standalone script to test ESPN league import without the web UI.

Usage:
    uv run python scripts/test_espn_import.py --league-id YOUR_LEAGUE_ID --season 2024 --swid YOUR_SWID --s2 YOUR_S2

Or set env vars:
    ESPN_LEAGUE_ID=123456 ESPN_SWID={...} ESPN_S2=... uv run python scripts/test_espn_import.py
"""

from __future__ import annotations

import argparse
import os
import sys

from ffpy.database import FFPyDatabase
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.league_api import _import_from_espn


def test_connection(league_id: int, season: int, swid: str, s2: str) -> bool:
    """Quick connectivity + auth test."""
    integration = ESPNLeagueIntegration(league_id, season, swid, s2)
    try:
        info = integration.get_league_info()
        print(f"✅ Connected to ESPN league: {info['name']}")
        print(f"   Teams: {info['size']}  |  Scoring: {info['scoring_type']}  |  Season: {info['season']}")
        return True
    except Exception as exc:
        print(f"❌ Failed to connect: {exc}")
        if "401" in str(exc) or "403" in str(exc):
            print("   → Check your SWID and espn_s2 cookies (they may have expired).")
        elif "404" in str(exc):
            print("   → Check your league_id and season year.")
        return False


def test_teams(league_id: int, season: int, swid: str, s2: str):
    """Fetch and display teams."""
    integration = ESPNLeagueIntegration(league_id, season, swid, s2)
    teams = integration.get_all_teams()
    print(f"\n📋 Teams ({len(teams)} found):")
    for t in teams:
        print(f"   {t['id']:3d} | {t['name']:<20} | W:{t['wins']} L:{t['losses']} | PF:{t['points_for']:.1f}")
    return teams


def test_rosters(league_id: int, season: int, swid: str, s2: str, team_id: int | None = None):
    """Fetch rosters for one or all teams."""
    integration = ESPNLeagueIntegration(league_id, season, swid, s2)
    if team_id:
        roster = integration.get_team_roster(team_id)
        print(f"\n🏈 Roster for team {team_id} ({len(roster)} players):")
        print(roster[["player", "position", "team", "lineup_slot"]].to_string(index=False))
    else:
        rosters = integration.get_league_rosters()
        print(f"\n🏈 Rosters for {len(rosters)} teams:")
        for tid, roster in rosters.items():
            print(f"\n--- Team {tid} ({len(roster)} players) ---")
            if not roster.empty:
                print(roster[["player", "position", "lineup_slot"]].head(5).to_string(index=False))


def test_matchups(league_id: int, season: int, swid: str, s2: str, week: int = 1):
    """Fetch matchups for a single week."""
    integration = ESPNLeagueIntegration(league_id, season, swid, s2)
    matchups = integration.get_matchups(week)
    print(f"\n⚔️  Matchups for Week {week} ({len(matchups)} found):")
    for m in matchups:
        print(f"   {m['home_team_id']} ({m['home_score']:.1f}) vs {m['away_team_id']} ({m['away_score']:.1f})")


def test_full_import(league_id: int, season: int, swid: str, s2: str, persist: bool = False):
    """Run the exact same import path the web UI uses."""
    print("\n🔄 Running full import (same as web UI)...")
    data = _import_from_espn(str(league_id), season, {"swid": swid, "s2": s2})

    league = data["league"]
    teams = data["teams"]
    matchups = data["matchups"]

    print("\n✅ Import successful!")
    print(f"   League: {league['name']} ({league['league_id']})")
    print(f"   Teams:  {len(teams)}")
    print(f"   Matchups: {len(matchups)}")

    if persist:
        db = FFPyDatabase()
        try:
            # Need a fake user_id for local testing
            league_id_stored = db.store_user_league("test_user", data)
            print(f"\n💾 Stored in local database: {league_id_stored}")

            # Verify round-trip
            stored_league = db.get_user_league(league_id_stored, "test_user")
            stored_teams = db.get_league_teams(league_id_stored, "test_user")
            print(f"   DB verify: {stored_league['league_name']} | {len(stored_teams)} teams")
        finally:
            db.close()

    return data


def main():
    parser = argparse.ArgumentParser(description="Test ESPN league import")
    parser.add_argument("--league-id", type=int, default=int(os.getenv("ESPN_LEAGUE_ID", "0")), help="Your ESPN league ID")
    parser.add_argument("--season", type=int, default=int(os.getenv("NFL_SEASON", "2024")))
    parser.add_argument("--swid", default=os.getenv("ESPN_SWID", ""), help="ESPN SWID cookie")
    parser.add_argument("--s2", default=os.getenv("ESPN_S2", ""), help="ESPN s2 cookie")
    parser.add_argument("--team-id", type=int, default=None, help="Test roster for a specific team ID")
    parser.add_argument("--week", type=int, default=1, help="Test matchups for a specific week")
    parser.add_argument("--persist", action="store_true", help="Store the full import in your local SQLite DB")
    parser.add_argument("--full", action="store_true", help="Run full import test (default: just connectivity)")
    args = parser.parse_args()

    if not args.league_id:
        print("Error: --league-id is required (or set ESPN_LEAGUE_ID env var)")
        sys.exit(1)

    print(f"Testing ESPN League {args.league_id} (Season {args.season})")
    print("=" * 50)

    # 1. Connectivity
    if not test_connection(args.league_id, args.season, args.swid, args.s2):
        sys.exit(1)

    # 2. Teams
    test_teams(args.league_id, args.season, args.swid, args.s2)

    # 3. Rosters (one team or all)
    test_rosters(args.league_id, args.season, args.swid, args.s2, args.team_id)

    # 4. Matchups
    test_matchups(args.league_id, args.season, args.swid, args.s2, args.week)

    # 5. Full import (same path as web UI)
    if args.full or args.persist:
        test_full_import(args.league_id, args.season, args.swid, args.s2, args.persist)

    print("\n" + "=" * 50)
    print("All ESPN tests passed! You can now import via the web UI.")
    print(f"   League ID: {args.league_id}")
    print(f"   Season:    {args.season}")
    print("\nWeb UI steps:")
    print("   1. Start the app:  uv run ffpy-web --port 8080")
    print("   2. Go to http://localhost:8080/league/")
    print("   3. Sign in → Import → ESPN → enter SWID + s2 → enter League ID + Season")


if __name__ == "__main__":
    main()
