"""FFPy database command-line interface.

Subcommands:
    migrate         Set up database schema.
    load            Load nflverse play-by-play data.
    update          Incrementally update the current season.
    collect-stats   Collect historical actual stats.
    prepare         Generate all app data required by the main UIs.
    mock            Generate realistic mock season data for development.

Run ``ffpy-db <subcommand> --help`` for per-command flags.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import pandas as pd

from ffpy.config import Config


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _setup_app_database(db_path: str | None = None):
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(db_path)
    print("Running play-by-play migration...")
    db.run_migration("002_play_by_play_schema.sql")
    print("[OK] Migration complete")
    return db


def _season_row_count(db, table: str, season: int) -> int:
    cursor = db.conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE season = ?", (season,))
    return int(cursor.fetchone()[0])


def cmd_migrate(args: argparse.Namespace) -> int:
    db = _setup_app_database(args.db_path)
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


def _normalise_nflverse_actual_stats(
    stats_df: pd.DataFrame,
    *,
    season: int,
    start_week: int,
    end_week: int,
) -> pd.DataFrame:
    if stats_df.empty:
        return pd.DataFrame()

    df = stats_df.copy()
    df = df[
        (df["season"] == season)
        & (df["week"].between(start_week, end_week))
        & (df["season_type"] == "REG")
        & (df["position"].isin(["QB", "RB", "WR", "TE"]))
    ].copy()
    if df.empty:
        return pd.DataFrame()

    points_col = "fantasy_points_ppr" if "fantasy_points_ppr" in df.columns else "fantasy_points"
    player_col = "player_display_name" if "player_display_name" in df.columns else "player_name"

    out = pd.DataFrame(
        {
            "player": df[player_col],
            "team": df["team"],
            "position": df["position"],
            "opponent": df.get("opponent_team", ""),
            "actual_points": df[points_col],
            "passing_yards": df.get("passing_yards", 0),
            "passing_tds": df.get("passing_tds", 0),
            "interceptions": df.get("passing_interceptions", 0),
            "rushing_yards": df.get("rushing_yards", 0),
            "rushing_tds": df.get("rushing_tds", 0),
            "receiving_yards": df.get("receiving_yards", 0),
            "receiving_tds": df.get("receiving_tds", 0),
            "receptions": df.get("receptions", 0),
            "week": df["week"],
            "nfl_id": df.get("player_id"),
        }
    )

    numeric_cols = [
        "actual_points",
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "receiving_yards",
        "receiving_tds",
        "receptions",
    ]
    out[numeric_cols] = out[numeric_cols].fillna(0)
    return out.sort_values(["week", "position", "player"]).reset_index(drop=True)


def _load_nflverse_actual_stats(season: int, start_week: int, end_week: int) -> pd.DataFrame:
    import nflreadpy as nfl

    stats = nfl.load_player_stats(seasons=[season], summary_level="week")
    return _normalise_nflverse_actual_stats(
        stats.to_pandas(),
        season=season,
        start_week=start_week,
        end_week=end_week,
    )


def _collect_nflverse_actual_stats(
    *,
    season: int,
    start_week: int,
    end_week: int,
    db_path: str | None = None,
) -> int:
    from ffpy.database import FFPyDatabase

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    stats = _load_nflverse_actual_stats(season, start_week, end_week)
    db = FFPyDatabase(db_path=db_path)
    total = 0
    try:
        print(f"Collecting actual stats from nflverse for {season}, weeks {start_week}-{end_week}")
        for week in range(start_week, end_week + 1):
            print(f"[Week {week}/{end_week}] ", end="", flush=True)
            if db.check_api_request("nflverse", season, week, "actuals"):
                print("already collected, skipping")
                continue

            week_df = stats[stats["week"] == week].copy()
            if week_df.empty:
                print("no data")
                db.log_api_request("nflverse", season, week, "actuals", False, "No data returned")
                continue

            db.store_actual_stats(week_df, season=season, week=week, source="nflverse")
            db.log_api_request("nflverse", season, week, "actuals", True)
            total += len(week_df)
            print(f"stored {len(week_df)} players")

        print(f"\nDone. Stored {total} player-week records at {db.db_path}")
        return total
    finally:
        db.close()


def _collect_espn_actual_stats(
    *,
    season: int,
    start_week: int,
    end_week: int,
    db_path: str | None = None,
    request_pause_seconds: float = 1.0,
) -> int:
    from ffpy.database import FFPyDatabase
    from ffpy.integrations import ESPNIntegration

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    db = FFPyDatabase(db_path=db_path)
    espn = ESPNIntegration()
    total = 0
    try:
        print(f"Collecting actual stats for {season}, weeks {start_week}-{end_week}")
        for week in range(start_week, end_week + 1):
            print(f"[Week {week}/{end_week}] ", end="", flush=True)
            if db.check_api_request("espn", season, week, "actuals"):
                print("already collected, skipping")
                continue
            try:
                df = espn.get_actual_stats(week=week, season=season)
            except Exception as exc:
                print(f"ERROR: {exc}")
                db.log_api_request("espn", season, week, "actuals", False, str(exc))
                continue

            if df.empty:
                print("no data")
                db.log_api_request("espn", season, week, "actuals", False, "No data returned")
                continue

            db.store_actual_stats(df, season=season, week=week, source="espn")
            db.log_api_request("espn", season, week, "actuals", True)
            total += len(df)
            print(f"stored {len(df)} players")

            if request_pause_seconds > 0 and week < end_week:
                time.sleep(request_pause_seconds)

        print(f"\nDone. Stored {total} player-week records at {db.db_path}")
        return total
    finally:
        db.close()


def _collect_actual_stats(
    *,
    source: str,
    season: int,
    start_week: int,
    end_week: int,
    db_path: str | None = None,
) -> int:
    if source == "nflverse":
        return _collect_nflverse_actual_stats(
            season=season,
            start_week=start_week,
            end_week=end_week,
            db_path=db_path,
        )
    if source == "espn":
        return _collect_espn_actual_stats(
            season=season,
            start_week=start_week,
            end_week=end_week,
            db_path=db_path,
        )
    raise ValueError(f"Unsupported stats source: {source}")


def cmd_collect_stats(args: argparse.Namespace) -> int:
    _collect_actual_stats(
        source=args.source,
        season=args.season,
        start_week=args.start_week,
        end_week=args.end_week,
        db_path=args.db_path,
    )
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    if args.start_week > args.end_week:
        raise ValueError("START_WEEK must be <= END_WEEK")
    if args.skip_pbp and args.skip_stats:
        print("Nothing to do: both --skip-pbp and --skip-stats were provided.")
        return 0

    _setup_logging(not args.quiet)

    mode = "mock" if args.mock else "real"
    print(f"Preparing FFPy app data for {args.season} ({mode})")

    db = _setup_app_database(args.db_path)
    resolved_db_path = str(db.db_path)
    try:
        if args.mock:
            from ffpy.mock import generate_pickem_game_data, generate_season_data

            db.close()
            db = None

            if not args.skip_pbp:
                generate_pickem_game_data(
                    season=args.season,
                    start_week=args.start_week,
                    weeks=args.end_week,
                    db_path=resolved_db_path,
                )
            if not args.skip_stats:
                generate_season_data(
                    season=args.season,
                    start_week=args.start_week,
                    weeks=args.end_week,
                    db_path=resolved_db_path,
                )
        else:
            from ffpy.nflverse_loader import NFLVerseLoader

            if not args.skip_pbp:
                existing_plays = _season_row_count(db, "plays", args.season)
                if existing_plays > 0 and not args.refresh_pbp:
                    print(
                        f"Play-by-play already loaded for {args.season} "
                        f"({existing_plays:,} plays); skipping. Use --refresh-pbp to reload."
                    )
                else:
                    with NFLVerseLoader(db) as loader:
                        loader.load_season(
                            season=args.season,
                            include_ftn=not args.no_ftn,
                            include_snaps=not args.no_snaps,
                            verbose=not args.quiet,
                        )
                        if args.validate:
                            v = loader.validate_data_quality(args.season)
                            print(f"\nQuality Score: {v['quality_score']:.1f}%")
                            print(f"  Total Plays:  {v['total_plays']:,}")
                            print(f"  Total Games:  {v['total_games']:,}")
                            if v.get("missing_player_ids"):
                                print(f"  Missing Player IDs: {v['missing_player_ids']}")
                            if v.get("missing_epa"):
                                print(f"  Missing EPA: {v['missing_epa']}")

            db.close()
            db = None

            if not args.skip_stats:
                _collect_actual_stats(
                    source=args.stats_source,
                    season=args.season,
                    start_week=args.start_week,
                    end_week=args.end_week,
                    db_path=resolved_db_path,
                )

        print(f"\nApp data ready. Database: {resolved_db_path}")
        return 0
    finally:
        if db is not None:
            db.close()


def cmd_mock(args: argparse.Namespace) -> int:
    from ffpy.mock import generate_season_data

    generate_season_data(season=args.season, weeks=args.weeks, db_path=args.db_path)
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

    p = sub.add_parser("collect-stats", help="Collect historical actual stats")
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--start-week", type=int, default=1)
    p.add_argument("--end-week", type=int, default=17)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument(
        "--source",
        choices=["nflverse", "espn"],
        default="nflverse",
        help="Stats source (default: nflverse; ESPN is unofficial and may be blocked)",
    )
    p.set_defaults(func=cmd_collect_stats)

    p = sub.add_parser(
        "prepare",
        help="Generate all app data needed for projections, play analysis, and pick'em",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--start-week", type=int, default=1)
    p.add_argument("--end-week", type=int, default=17)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--mock", action="store_true", help="Generate mock data instead of pulling nflverse/ESPN")
    p.add_argument("--skip-pbp", action="store_true", help="Skip games/play-by-play data")
    p.add_argument("--skip-stats", action="store_true", help="Skip player actual stats")
    p.add_argument(
        "--stats-source",
        choices=["nflverse", "espn"],
        default="nflverse",
        help="Actual-stats source in real mode (default: nflverse)",
    )
    p.add_argument("--no-ftn", action="store_true", help="Skip FTN charting in real mode")
    p.add_argument("--no-snaps", action="store_true", help="Skip snap counts in real mode")
    p.add_argument("--refresh-pbp", action="store_true", help="Reload play-by-play even if the season exists")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.add_argument(
        "--validate", action="store_true", help="Validate play-by-play data quality after real load"
    )
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("mock", help="Generate realistic mock season data (for development)")
    p.add_argument("--season", type=int, default=2024)
    p.add_argument("--weeks", type=int, default=17)
    p.add_argument("--db-path", help="Custom database path")
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
