"""ffpy-ingest CLI — ingest league data from ESPN, Yahoo, and Sleeper.

Usage:
    ffpy-ingest espn <league_id> [--season N] [--json|--csv] [--db PATH] [--swid ...] [--s2 ...]
    ffpy-ingest yahoo <league_id> [--season N] [--json|--csv] [--db PATH] [--token ...]
    ffpy-ingest sleeper <league_id> [--season N] [--json|--csv] [--db PATH]
    ffpy-ingest yahoo-auth
    ffpy-ingest yahoo-token --code CODE
    ffpy-ingest leagues-list [--json|--csv] [--db PATH]
    ffpy-ingest leagues-info <id> [--json|--csv] [--db PATH]
    ffpy-ingest roster <league_id> <team_id> [--json|--csv] [--db PATH]
    ffpy-ingest matchups <league_id> <week> [--json|--csv] [--db PATH]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any, List, Optional

from ffpy.database import FFPyDatabase
from ffpy.ingest import auth, espn, output, sleeper, yahoo

logger = logging.getLogger(__name__)


def _get_db(db_path: Optional[str] = None) -> FFPyDatabase:
    return FFPyDatabase(db_path=db_path)


def _format_and_exit(data: Any, fmt: str) -> None:
    output.format_output(data, fmt)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: ingest
# ---------------------------------------------------------------------------


def cmd_ingest_espn(args: argparse.Namespace) -> None:
    data = espn.fetch_espn_league(
        league_id=args.league_id,
        season=args.season,
        swid=args.swid,
        espn_s2=args.s2,
    )
    if args.db is not None:
        output.persist_to_db(data, db_path=args.db or None)
    _format_and_exit(data, args.format)


def cmd_ingest_yahoo(args: argparse.Namespace) -> None:
    data = yahoo.fetch_yahoo_league(
        league_id=args.league_id,
        season=args.season,
        access_token=args.token,
    )
    if args.db is not None:
        output.persist_to_db(data, db_path=args.db or None)
    _format_and_exit(data, args.format)


def cmd_ingest_sleeper(args: argparse.Namespace) -> None:
    data = sleeper.fetch_sleeper_league(
        league_id=args.league_id,
        season=args.season,
    )
    if args.db is not None:
        output.persist_to_db(data, db_path=args.db or None)
    _format_and_exit(data, args.format)


# ---------------------------------------------------------------------------
# Subcommand: yahoo auth
# ---------------------------------------------------------------------------


def cmd_yahoo_auth(args: argparse.Namespace) -> None:
    """Run the Yahoo OAuth flow interactively."""
    client_id, client_secret, redirect_uri = yahoo.get_client_credentials()
    integration = yahoo.YahooIntegration(client_id, client_secret, redirect_uri)

    auth_url = integration.get_authorization_url(state="ffpy-ingest")
    print("\n1. Visit this URL in your browser:\n")
    print(f"   {auth_url}\n")
    print("2. Authorize the application")
    print("3. Copy the full redirect URL and paste it below\n")

    redirect_response = input("Paste redirect URL or authorization code: ").strip()
    if "code=" in redirect_response:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(redirect_response)
        params = parse_qs(parsed.query)
        code = params.get("code", [""])[0]
    else:
        code = redirect_response

    if not code:
        print("Error: No authorization code provided")
        sys.exit(1)

    token = integration.exchange_code(code)
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    auth.save_yahoo_token(token)
    print(f"\nToken saved to {auth.TOKEN_FILE}")
    print(f"Access token: {token['access_token'][:20]}... (expires at {token['expires_at']})")


def cmd_yahoo_token(args: argparse.Namespace) -> None:
    """Exchange an OAuth code for a token (non-interactive)."""
    client_id, client_secret, redirect_uri = yahoo.get_client_credentials()
    integration = yahoo.YahooIntegration(client_id, client_secret, redirect_uri)

    code = args.code
    token = integration.exchange_code(code)
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    auth.save_yahoo_token(token)
    print(f"Token saved to {auth.TOKEN_FILE}")


# ---------------------------------------------------------------------------
# Subcommand: leagues
# ---------------------------------------------------------------------------


def cmd_leagues_list(args: argparse.Namespace) -> None:
    db = _get_db(args.db or None)
    try:
        leagues = db.get_all_leagues()
    finally:
        db.close()

    if not leagues:
        print("No imported leagues found.")
        sys.exit(0)

    rows = []
    for lg in leagues:
        rows.append(
            {
                "league_id": lg.get("league_id", ""),
                "provider": lg.get("provider", ""),
                "name": lg.get("league_name", ""),
                "season": str(lg.get("season", "")),
                "teams": str(lg.get("num_teams", "")),
            }
        )
    output.format_output(rows, args.format)


def cmd_leagues_info(args: argparse.Namespace) -> None:
    db = _get_db(args.db or None)
    try:
        league = db.get_league_by_id(args.id)
    finally:
        db.close()

    if not league:
        print(f"League '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)

    output.format_output(dict(league), args.format)


# ---------------------------------------------------------------------------
# Subcommand: roster
# ---------------------------------------------------------------------------


def cmd_roster(args: argparse.Namespace) -> None:
    db = _get_db(args.db or None)
    try:
        teams = db.get_teams_for_league(args.league_id)
    finally:
        db.close()

    if not teams:
        print(f"No teams found for league '{args.league_id}'", file=sys.stderr)
        sys.exit(1)

    team = next((t for t in teams if t["team_id"] == args.team_id), None)
    if not team:
        print(f"Team '{args.team_id}' not found in league '{args.league_id}'", file=sys.stderr)
        sys.exit(1)

    import json

    roster = json.loads(team.get("roster_json") or "[]")
    if not roster:
        print("Roster is empty")
        sys.exit(0)

    output.format_output(roster, args.format)


# ---------------------------------------------------------------------------
# Subcommand: matchups
# ---------------------------------------------------------------------------


def cmd_matchups(args: argparse.Namespace) -> None:
    db = _get_db(args.db or None)
    try:
        matchups = db.get_matchups_for_league(args.league_id, args.week)
    finally:
        db.close()

    if not matchups:
        print(f"No matchups found for league '{args.league_id}' week {args.week}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for m in matchups:
        rows.append(
            {
                "week": m.get("week", ""),
                "home": m.get("home_team_id", ""),
                "away": m.get("away_team_id", ""),
                "home_score": m.get("home_score", ""),
                "away_score": m.get("away_score", ""),
            }
        )
    output.format_output(rows, args.format)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _common_parser() -> argparse.ArgumentParser:
    """Shared flags that work after any subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db",
        nargs="?",
        const="",
        default=None,
        help="Also persist to SQLite (optional path; default: ~/.ffpy/ffpy.db)",
    )
    common.add_argument(
        "--json", action="store_const", dest="format", const="json", default="table", help="Output as JSON"
    )
    common.add_argument("--csv", action="store_const", dest="format", const="csv", help="Output as CSV")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="ffpy-ingest",
        description="Ingest fantasy league data from ESPN, Yahoo, and Sleeper.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- ingest espn ---
    ingest_espn = sub.add_parser("espn", parents=[common], help="Ingest ESPN league data")
    ingest_espn.add_argument("league_id", help="ESPN league ID (from URL)")
    ingest_espn.add_argument("--season", type=int, default=2025, help="Season year (default: 2025)")
    ingest_espn.add_argument("--swid", default=None, help="ESPN SWID cookie (for private leagues)")
    ingest_espn.add_argument("--s2", default=None, help="ESPN S2 cookie (for private leagues)")
    ingest_espn.set_defaults(func=cmd_ingest_espn)

    # --- ingest yahoo ---
    ingest_yahoo = sub.add_parser("yahoo", parents=[common], help="Ingest Yahoo league data")
    ingest_yahoo.add_argument("league_id", help="Yahoo league key (e.g. 389.l.12345)")
    ingest_yahoo.add_argument("--season", type=int, default=2025, help="Season year (default: 2025)")
    ingest_yahoo.add_argument("--token", default=None, help="Yahoo OAuth access token")
    ingest_yahoo.set_defaults(func=cmd_ingest_yahoo)

    # --- ingest sleeper ---
    ingest_sleeper = sub.add_parser("sleeper", parents=[common], help="Ingest Sleeper league data")
    ingest_sleeper.add_argument("league_id", help="Sleeper league ID")
    ingest_sleeper.add_argument("--season", type=int, default=2025, help="Season year (default: 2025)")
    ingest_sleeper.set_defaults(func=cmd_ingest_sleeper)

    # --- yahoo auth ---
    yahoo_auth = sub.add_parser("yahoo-auth", help="Run Yahoo OAuth flow")
    yahoo_auth.set_defaults(func=cmd_yahoo_auth)

    # --- yahoo token ---
    yahoo_token = sub.add_parser("yahoo-token", help="Exchange Yahoo OAuth code for token")
    yahoo_token.add_argument("--code", required=True, help="OAuth authorization code")
    yahoo_token.set_defaults(func=cmd_yahoo_token)

    # --- leagues list ---
    leagues_list = sub.add_parser("leagues-list", parents=[common], help="List imported leagues from DB")
    leagues_list.set_defaults(func=cmd_leagues_list)

    # --- leagues info ---
    leagues_info = sub.add_parser("leagues-info", parents=[common], help="Show imported league details")
    leagues_info.add_argument("id", help="League ID (prefixed, e.g. espn:123456)")
    leagues_info.set_defaults(func=cmd_leagues_info)

    # --- roster ---
    roster = sub.add_parser("roster", parents=[common], help="Show team roster from DB")
    roster.add_argument("league_id", help="League ID (prefixed)")
    roster.add_argument("team_id", help="Team ID (prefixed)")
    roster.set_defaults(func=cmd_roster)

    # --- matchups ---
    matchups = sub.add_parser("matchups", parents=[common], help="Show week matchups from DB")
    matchups.add_argument("league_id", help="League ID (prefixed)")
    matchups.add_argument("week", type=int, help="Week number (1-17)")
    matchups.set_defaults(func=cmd_matchups)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
