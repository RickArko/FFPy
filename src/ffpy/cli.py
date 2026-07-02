"""FFPy database command-line interface.

Subcommands:
    migrate         Set up database schema.
    load            Load nflverse play-by-play data.
    update          Incrementally update the current season.
    collect-stats   Collect historical actual stats.
    prepare         Generate all app data required by the main UIs.
    mock            Generate realistic mock season data for development.
    compute-stats   Compute derived advanced player stats (Phase 1).
    load-ngs        Load Next Gen Stats from nflverse (Phase 2A).
    load-injuries   Load injury data from nflverse (Phase 2B).
    audit           Run data quality checks.

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
    from ffpy.nflverse import NFLVerseLoader, setup_database

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
    from ffpy.nflverse import NFLVerseLoader, setup_database

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
            from ffpy.nflverse import NFLVerseLoader

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

                # Load rosters unless skipped
                if not args.skip_rosters:
                    try:
                        with NFLVerseLoader(db) as loader:
                            loader.load_rosters(season=args.season, verbose=not args.quiet)
                    except Exception as e:
                        print(f"  [WARN] Could not load rosters: {e}")

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


def cmd_compute_stats(args: argparse.Namespace) -> int:
    from ffpy.nflverse import NFLVerseLoader, setup_database

    db = setup_database(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            stats = loader.compute_advanced_stats(season=args.season, verbose=True)
        print(f"\nStored {stats.get('stored', 0)} advanced stat rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_ngs(args: argparse.Namespace) -> int:
    from ffpy.nflverse import NFLVerseLoader, setup_database

    db = setup_database(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            stats = loader.load_nextgen(season=args.season, verbose=True)
        print(f"\nStored {stats.get('stored', 0)} NGS rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_injuries(args: argparse.Namespace) -> int:
    from ffpy.nflverse import NFLVerseLoader, setup_database

    db = setup_database(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            stats = loader.load_injuries(season=args.season, verbose=True)
        print(f"\nStored {stats.get('stored', 0)} injury rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_dfs(args: argparse.Namespace) -> int:
    from ffpy.database import FFPyDatabase
    from ffpy.integrations.dfs import fetch_all_platforms

    platforms = args.platforms.split(",") if args.platforms else None
    data = fetch_all_platforms(args.season, args.week, platforms)
    total = 0
    db = FFPyDatabase(args.db_path)
    try:
        for platform, df in data.items():
            if df.empty:
                print(f"  {platform}: no data")
                continue
            count = db.store_dfs_salaries(df, args.season, args.week, platform)
            total += count
            print(f"  {platform}: stored {count} rows")
        print(f"\nTotal: {total} DFS salary rows")
        return 0
    finally:
        db.close()


def cmd_load_adp(args: argparse.Namespace) -> int:
    from ffpy.database import FFPyDatabase
    from ffpy.integrations.adp import fetch_all_platforms

    platforms = args.platforms.split(",") if args.platforms else None
    data = fetch_all_platforms(args.season, platforms)
    total = 0
    db = FFPyDatabase(args.db_path)
    try:
        for platform, df in data.items():
            if df.empty:
                print(f"  {platform}: no data")
                continue
            count = db.store_adp(df, args.season)
            total += count
            print(f"  {platform}: stored {count} rows")
        print(f"\nTotal: {total} ADP rows")
        return 0
    finally:
        db.close()


def cmd_compute_ol_stats(args: argparse.Namespace) -> int:
    """Compute offensive line stats from play-by-play data."""
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        df = db.compute_offensive_line_stats(season=args.season, weeks=args.weeks)
        if df.empty:
            if not args.quiet:
                print("  [WARN] No play data to compute offensive line stats from.")
            return 0
        stored = db.store_offensive_line_stats(df, args.season)
        if stored > 0 and not args.quiet:
            print(f"  [OK] Stored {stored} offensive line stat rows for {args.season}")
        return 0
    finally:
        db.close()


def cmd_load_rosters(args: argparse.Namespace) -> int:
    """Load player roster and bio data from nflreadpy."""
    from ffpy.database import FFPyDatabase
    from ffpy.nflverse import NFLVerseLoader

    db = FFPyDatabase(args.db_path)
    try:
        with NFLVerseLoader(db) as loader:
            stats = loader.load_rosters(season=args.season, verbose=not args.quiet)
        if not args.quiet:
            print(f"\nStored {stats.get('stored', 0)} roster rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_cfb_games(args: argparse.Namespace) -> int:
    """Load college football game schedules."""
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_games(season=args.season, verbose=not args.quiet)
        if not args.quiet:
            print(f"\nStored {stats.get('stored', 0)} CFB games for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_cfb_rosters(args: argparse.Namespace) -> int:
    """Load college football roster data."""
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_rosters(season=args.season, verbose=not args.quiet)
        if not args.quiet:
            print(f"\nStored {stats.get('stored', 0)} CFB roster rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_cfb_pbp(args: argparse.Namespace) -> int:
    """Load college football play-by-play data."""
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_pbp(season=args.season, verbose=not args.quiet)
        if not args.quiet:
            print(
                f"\nStored {stats.get('games', 0)} CFB games and "
                f"{stats.get('plays', 0):,} plays for {args.season}."
            )
        return 0
    finally:
        db.close()


def cmd_load_cfb(args: argparse.Namespace) -> int:
    """Load college football games, rosters, and optionally PBP."""
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_season(
                season=args.season,
                include_games=not args.skip_games,
                include_rosters=not args.skip_rosters,
                include_pbp=args.pbp,
                verbose=not args.quiet,
            )
        if not args.quiet:
            print(
                f"\nCFB load complete for {args.season}: "
                f"{stats.get('games', 0)} games, "
                f"{stats.get('rosters', 0)} roster rows, "
                f"{stats.get('plays', 0):,} plays."
            )
        return 0
    finally:
        db.close()


def _parse_cfb_conferences(raw: str) -> list[str]:
    from ffpy.integrations.cfbd import DEFAULT_CONFERENCES

    if not raw or not raw.strip():
        return list(DEFAULT_CONFERENCES)
    return [part.strip() for part in raw.split(",") if part.strip()]


def cmd_load_cfb_teams(args: argparse.Namespace) -> int:
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.database import FFPyDatabase

    confs = _parse_cfb_conferences(args.conferences)
    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_teams(args.season, conferences=confs, verbose=not args.quiet)
        if not args.quiet:
            print(f"Stored {stats.get('stored', 0)} CFB teams for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_load_cfb_stats(args: argparse.Namespace) -> int:
    from ffpy.cfbverse import CFBVerseLoader
    from ffpy.config import Config
    from ffpy.database import FFPyDatabase

    if not Config.is_cfbd_configured():
        print("[ERROR] CFBD_API_KEY is required. Set it in .env")
        return 1
    confs = _parse_cfb_conferences(args.conferences)
    db = FFPyDatabase(args.db_path)
    try:
        with CFBVerseLoader(db) as loader:
            stats = loader.load_cfbd_stats(
                args.season,
                conferences=confs,
                start_week=args.start_week,
                end_week=args.end_week,
                verbose=not args.quiet,
            )
        if not args.quiet:
            print(f"CFB stats load complete: {stats}")
        return 0
    finally:
        db.close()


def cmd_build_cfb_players(args: argparse.Namespace) -> int:
    from ffpy.cfb_players import build_cfb_players
    from ffpy.database import FFPyDatabase

    confs = _parse_cfb_conferences(args.conferences)
    db = FFPyDatabase(args.db_path)
    try:
        stats = build_cfb_players(db, args.season, conferences=confs)
        if not args.quiet:
            print(f"Built {stats.get('players', 0)} players, {stats.get('id_maps', 0)} ID maps.")
        return 0
    finally:
        db.close()


def cmd_compute_cfb_fantasy(args: argparse.Namespace) -> int:
    from ffpy.cfb_stats import compute_cfb_fantasy_points
    from ffpy.database import FFPyDatabase

    confs = _parse_cfb_conferences(args.conferences)
    db = FFPyDatabase(args.db_path)
    try:
        stored = compute_cfb_fantasy_points(
            db,
            args.season,
            scoring_preset=args.preset,
            fcs_discount=args.fcs_discount,
            conferences=confs,
        )
        if not args.quiet:
            print(f"Stored {stored} CFB fantasy point rows for {args.season}.")
        return 0
    finally:
        db.close()


def cmd_compute_cfb_projections(args: argparse.Namespace) -> int:
    from ffpy.cfb_projections import CfbProjectionModel
    from ffpy.database import FFPyDatabase

    confs = _parse_cfb_conferences(args.conferences)
    db = FFPyDatabase(args.db_path)
    try:
        with CfbProjectionModel(db) as model:
            if args.week:
                df = model.generate_projections(args.season, args.week, conferences=confs)
                if not args.quiet:
                    print(f"Generated {len(df)} projections for week {args.week}.")
            else:
                total = 0
                for week in range(args.start_week, args.end_week + 1):
                    df = model.generate_projections(args.season, week, conferences=confs)
                    total += len(df)
                if not args.quiet:
                    print(f"Generated {total} projections for weeks {args.start_week}-{args.end_week}.")
        return 0
    finally:
        db.close()


def cmd_audit_cfb(args: argparse.Namespace) -> int:
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        audit = db.audit_cfb_data(season=args.season)
        for key, val in sorted(audit.items()):
            print(f"  {key}: {val}")
        return 0
    finally:
        db.close()


def cmd_load_depth_charts(args: argparse.Namespace) -> int:
    from ffpy.integrations.depth_chart import fetch_nflverse_depth_charts
    from ffpy.nflverse import setup_database

    db = setup_database(args.db_path)
    try:
        df = fetch_nflverse_depth_charts(args.season, args.week if args.week else None)
        if df.empty:
            print("  [WARN] No depth chart data returned from nflreadpy.")
            return 0
        count = db.store_depth_charts(df, args.season)
        print(f"  [OK] Stored {count} depth chart rows")
        return 0
    finally:
        db.close()


def cmd_add_weather(args: argparse.Namespace) -> int:
    """Add historical weather data for a season from nflverse PBP."""
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)

    print(f"Loading play-by-play data for {args.season} to extract weather...")
    try:
        import nflreadpy as nfl

        pbp = nfl.load_pbp(seasons=[args.season])
    except Exception as e:
        print(f"  [ERR] Failed to load PBP: {e}")
        return 1

    if pbp is None or len(pbp) == 0:
        print("  [WARN] No PBP data available.")
        return 0

    import polars as pl

    weather_cols = ["game_id", "season", "week", "roof", "surface", "temp", "wind", "weather"]
    available = [c for c in weather_cols if c in pbp.columns]
    weather_df = pbp.select(available).unique(subset=["game_id"])

    # Parse the weather text field into structured columns
    if "weather" in weather_df.columns:
        # Extract temp and wind from weather text as fallback for missing numeric columns
        temp_from_text = pl.col("weather").str.extract(r"Temp:\s*(\d+)", 1).cast(pl.Int64)
        wind_from_text = pl.col("weather").str.extract(r"Wind:.*?(\d+)", 1).cast(pl.Int64)

        weather_df = weather_df.with_columns(
            [
                pl.when(pl.col("weather").str.contains("(?i)clear|sunny"))
                .then(pl.lit("Clear"))
                .when(pl.col("weather").str.contains("(?i)cloudy|mostly cloudy|partly cloudy"))
                .then(pl.lit("Cloudy"))
                .when(pl.col("weather").str.contains("(?i)rain|showers|drizzle"))
                .then(pl.lit("Rain"))
                .when(pl.col("weather").str.contains("(?i)snow|sleet|wintry"))
                .then(pl.lit("Snow"))
                .when(pl.col("weather").str.contains("(?i)fog|mist"))
                .then(pl.lit("Fog"))
                .when(pl.col("weather").str.contains("(?i)dome|indoors"))
                .then(pl.lit("Dome"))
                .otherwise(pl.lit("Unknown"))
                .alias("weather_condition"),
                pl.col("weather").str.extract(r"Humidity:\s*(\d+)", 1).cast(pl.Int64).alias("humidity"),
                # Fill missing temp/wind from weather text
                pl.col("temp").fill_null(temp_from_text).alias("temp"),
                pl.col("wind").fill_null(wind_from_text).alias("wind"),
                pl.col("weather").alias("weather_description"),
            ]
        )

    pandas_df = weather_df.to_pandas()

    if pandas_df.empty:
        print("  [WARN] No weather data extracted.")
        return 0

    count = db.store_game_weather(pandas_df)
    print(f"  [OK] Stored weather data for {count} games in {args.season}.")

    # --- Augment indoor/dome games with sensible defaults ---
    indoor_roofs = {"dome", "closed", "open"}
    indoor = (
        pandas_df["roof"].str.lower().isin(indoor_roofs) if "roof" in pandas_df.columns else pd.Series(False)
    )
    needs_default = indoor & pandas_df["temp"].isna()
    n_filled = 0
    if needs_default.any():
        cursor = db.conn.cursor()
        for _, row in pandas_df[needs_default].iterrows():
            cursor.execute(
                """UPDATE game_weather
                   SET temp = 72, wind = 0, humidity = 50,
                       weather_condition = COALESCE(weather_condition, 'Dome'),
                       weather_description = COALESCE(weather_description, 'Dome, climate-controlled')
                   WHERE game_id = ?""",
                (row["game_id"],),
            )
        db.conn.commit()
        n_filled = int(needs_default.sum())
        print(f"  [AU] Filled {n_filled} indoor games with dome defaults (72°F, 0 wind).")

    # Re-read from DB to get accurate counts
    result = db.get_game_weather(season=args.season)
    total = len(result)
    with_temp = int(result["temp"].notna().sum())
    print(f"       {with_temp}/{total} games have temperature data.")

    # Warn about remaining outdoor gaps
    if "roof" in result.columns:
        outdoor_missing = result[(result["roof"].str.lower() == "outdoors") & (result["temp"].isna())]
        if not outdoor_missing.empty:
            print(f"  [WARN] {len(outdoor_missing)} outdoor games still missing weather data.")

    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(args.db_path)
    try:
        results = db.audit_data_quality()

        print(f"\n{'=' * 50}")
        print("Data Quality Audit")
        print(f"{'=' * 50}")

        # Views
        for key, value in results.items():
            if key.startswith("view_"):
                status = "OK" if value else "MISSING"
                print(f"  {key:30s} {status}")

        # Row counts
        print("\n  --- Table Row Counts ---")
        for key, value in sorted(results.items()):
            if key.startswith("table_"):
                name = key.replace("table_", "").replace("_rows", "")
                print(f"  {name:25s} {value:>8,}")

        # Issues
        missing = results.get("missing_games_count", -1)
        dups = results.get("duplicate_stat_weeks", -1)
        print("\n  --- Issues ---")
        print(f"  Missing games:            {missing:>8,}")
        print(f"  Duplicate stat weeks:     {dups:>8,}")

        if args.fix:
            print("\n  Auto-fix not yet implemented (coming in a future release).")

        if args.exit_zero:
            return 0
        return 1 if (missing > 0 or dups > 0) else 0
    finally:
        db.close()


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
    p.add_argument("--skip-rosters", action="store_true", help="Skip player rosters in real mode")
    p.add_argument("--refresh-pbp", action="store_true", help="Reload play-by-play even if the season exists")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.add_argument(
        "--validate", action="store_true", help="Validate play-by-play data quality after real load"
    )
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser(
        "compute-stats",
        help="Compute derived advanced player stats from existing plays + snaps + FTN",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_compute_stats)

    p = sub.add_parser(
        "load-ngs",
        help="Load Next Gen Stats from nflverse (passing / receiving / rushing)",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_load_ngs)

    p = sub.add_parser(
        "load-injuries",
        help="Load player injury data from nflverse",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_load_injuries)

    p = sub.add_parser(
        "audit",
        help="Run data quality checks against all tables and views",
    )
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible (limited support)",
    )
    p.add_argument(
        "--exit-zero",
        action="store_true",
        help="Exit with code 0 even if issues found (warnings only)",
    )
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser(
        "load-dfs",
        help="Load DFS salaries (Phase 3 — stub, requires API integration)",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--week", type=int, default=1)
    p.add_argument("--platforms", default="", help="Comma-separated list (draftkings,fanduel)")
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_load_dfs)

    p = sub.add_parser(
        "load-adp",
        help="Load ADP data (Phase 3 — stub, requires API integration)",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--platforms", default="", help="Comma-separated list (fantasypros,underdog)")
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_load_adp)

    p = sub.add_parser(
        "load-depth-charts",
        help="Load depth charts from nflreadpy",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--week", type=int, default=None, help="Optional week filter")
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_load_depth_charts)

    p = sub.add_parser(
        "load-rosters",
        help="Load player roster & bio data from nflreadpy",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.set_defaults(func=cmd_load_rosters)

    p = sub.add_parser(
        "load-cfb",
        help="Load college football games + rosters (optional PBP via --pbp)",
    )
    p.add_argument("--season", type=int, required=True, help="CFB season year")
    p.add_argument("--pbp", action="store_true", help="Also load play-by-play (large download)")
    p.add_argument("--skip-games", action="store_true", help="Skip game schedule load")
    p.add_argument("--skip-rosters", action="store_true", help="Skip roster load")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.set_defaults(func=cmd_load_cfb)

    p = sub.add_parser("load-cfb-games", help="Load college football game schedules")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_load_cfb_games)

    p = sub.add_parser("load-cfb-rosters", help="Load college football rosters")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_load_cfb_rosters)

    p = sub.add_parser("load-cfb-pbp", help="Load college football play-by-play")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_load_cfb_pbp)

    p = sub.add_parser("load-cfb-teams", help="Load CFB teams for SEC/B1G/ACC (CFBD or ESPN fallback)")
    p.add_argument("--season", type=int, required=True)
    p.add_argument(
        "--conferences",
        default="SEC,Big Ten,ACC",
        help="Comma-separated conferences (default: SEC,Big Ten,ACC)",
    )
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_load_cfb_teams)

    p = sub.add_parser("load-cfb-stats", help="Load CFB player/team game stats from CFBD API")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--conferences", default="SEC,Big Ten,ACC")
    p.add_argument("--start-week", type=int, default=1)
    p.add_argument("--end-week", type=int, default=16)
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_load_cfb_stats)

    p = sub.add_parser("build-cfb-players", help="Build CFB player registry and ESPN↔CFBD ID map")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--conferences", default="SEC,Big Ten,ACC")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_build_cfb_players)

    p = sub.add_parser("compute-cfb-fantasy", help="Compute CFB weekly fantasy points")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--preset", default="college_standard")
    p.add_argument("--fcs-discount", type=float, default=0.75)
    p.add_argument("--conferences", default="SEC,Big Ten,ACC")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_compute_cfb_fantasy)

    p = sub.add_parser("compute-cfb-projections", help="Generate CFB player projections")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, default=None)
    p.add_argument("--start-week", type=int, default=1)
    p.add_argument("--end-week", type=int, default=16)
    p.add_argument("--conferences", default="SEC,Big Ten,ACC")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_compute_cfb_projections)

    p = sub.add_parser("audit-cfb", help="Audit CFB fantasy data coverage")
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_audit_cfb)

    p = sub.add_parser(
        "compute-ol-stats",
        help="Compute offensive line stats from play-by-play data",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--weeks", type=int, default=4, help="Rolling window size")
    p.add_argument("--db-path", help="Custom database path")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.set_defaults(func=cmd_compute_ol_stats)

    p = sub.add_parser(
        "add-weather",
        help="Add historical weather data for a season from nflverse PBP",
    )
    p.add_argument("--season", type=int, default=Config.NFL_SEASON)
    p.add_argument("--db-path", help="Custom database path")
    p.set_defaults(func=cmd_add_weather)

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
