"""FFPy database command-line interface.

Subcommands:
    migrate         Set up database schema.
    load            Load nflverse play-by-play data.
    update          Incrementally update the current season.
    collect-stats   Collect historical actual stats from ESPN.
    mock            Generate realistic mock season data for development.

Run ``ffpy-db <subcommand> --help`` for per-command flags.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from ffpy.config import Config


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_migrate(args: argparse.Namespace) -> int:
    from ffpy.nflverse_loader import setup_database

    db = setup_database(args.db_path)
    try:
        print(f"Database ready: {db.db_path}")
    finally:
        db.close()
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    from ffpy.nflverse_loader import NFLVerseLoader, setup_database

    _setup_logging(not args.quiet)

    # Default to the current NFL season when neither flag is given.
    season = args.season
    if season is None and args.start_season is None:
        season = Config.NFL_SEASON
        print(f"No --season / --start-season given; defaulting to {season} (from NFL_SEASON).")

    db = setup_database(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            if season is not None:
                loader.load_season(
                    season=season,
                    include_ftn=not args.no_ftn,
                    include_snaps=not args.no_snaps,
                    verbose=not args.quiet,
                )
                if args.validate:
                    v = loader.validate_data_quality(season)
                    print(f"\nQuality Score: {v['quality_score']:.1f}%")
                    print(f"  Total Plays:  {v['total_plays']:,}")
                    print(f"  Total Games:  {v['total_games']:,}")
                    if v.get("missing_player_ids"):
                        print(f"  Missing Player IDs: {v['missing_player_ids']}")
                    if v.get("missing_epa"):
                        print(f"  Missing EPA: {v['missing_epa']}")
            else:
                end_season = args.end_season or Config.NFL_SEASON
                loader.load_historical(
                    start_season=args.start_season,
                    end_season=end_season,
                    include_ftn=not args.no_ftn,
                    include_snaps=not args.no_snaps,
                    verbose=not args.quiet,
                )
        print(f"\nLoad complete. Database: {db.db_path}")
        return 0
    finally:
        db.close()


def cmd_update(args: argparse.Namespace) -> int:
    from ffpy.nflverse_loader import NFLVerseLoader, setup_database

    _setup_logging(not args.quiet)
    db = setup_database(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            stats = loader.update_current_season(verbose=not args.quiet)
        if stats["plays"] == 0:
            print("Already up to date.")
        else:
            print(f"Added {stats['plays']} new plays.")
        return 0
    finally:
        db.close()


def cmd_collect_stats(args: argparse.Namespace) -> int:
    from ffpy.database import FFPyDatabase
    from ffpy.integrations import ESPNIntegration

    db = FFPyDatabase()
    espn = ESPNIntegration()
    total = 0
    try:
        print(f"Collecting actual stats for {args.season}, weeks {args.start_week}-{args.end_week}")
        for week in range(args.start_week, args.end_week + 1):
            print(f"[Week {week}/{args.end_week}] ", end="", flush=True)
            if db.check_api_request("espn", args.season, week, "actuals"):
                print("already collected, skipping")
                continue
            try:
                df = espn.get_actual_stats(week=week, season=args.season)
            except Exception as exc:
                print(f"ERROR: {exc}")
                db.log_api_request("espn", args.season, week, "actuals", False, str(exc))
                continue

            if df.empty:
                print("no data")
                db.log_api_request("espn", args.season, week, "actuals", False, "No data returned")
                continue

            db.store_actual_stats(df, season=args.season, week=week, source="espn")
            db.log_api_request("espn", args.season, week, "actuals", True)
            total += len(df)
            print(f"stored {len(df)} players")

            if week < args.end_week:
                time.sleep(1)  # be polite to ESPN

        print(f"\nDone. Stored {total} player-week records at {db.db_path}")
        return 0
    finally:
        db.close()


def cmd_mock(args: argparse.Namespace) -> int:
    from ffpy.mock import generate_season_data

    generate_season_data(season=args.season, weeks=args.weeks)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ffpy-db",
        description="FFPy database CLI — manage play-by-play and stats data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("migrate", help="Set up database schema")
    p.add_argument("--db-path", help=f"Custom database path (default: {Config.DATABASE_PATH})")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser(
        "load",
        help="Load nflverse play-by-play data (defaults to NFL_SEASON from .env)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--season", type=int, help="Single season (e.g., 2024)")
    group.add_argument("--start-season", type=int, help="Start of season range")
    p.add_argument("--end-season", type=int, help="End of range (default: current NFL season)")
    p.add_argument("--no-ftn", action="store_true", help="Skip FTN charting (2022+ only)")
    p.add_argument("--no-snaps", action="store_true", help="Skip snap counts (2012+ only)")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.add_argument("--validate", action="store_true", help="Validate data quality after load")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("update", help="Incrementally update the current season")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("collect-stats", help="Collect historical actual stats from ESPN")
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--start-week", type=int, default=1)
    p.add_argument("--end-week", type=int, default=17)
    p.set_defaults(func=cmd_collect_stats)

    p = sub.add_parser("mock", help="Generate realistic mock season data (for development)")
    p.add_argument("--season", type=int, default=2024)
    p.add_argument("--weeks", type=int, default=17)
    p.set_defaults(func=cmd_mock)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
