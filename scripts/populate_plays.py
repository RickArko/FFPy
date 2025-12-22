#!/usr/bin/env python
"""
Populate the FFPy database with NFL play-by-play data.

This script loads historical play-by-play data from nflverse into the SQLite database.

Usage:
    # Load a single season
    uv run python scripts/populate_plays.py --season 2024

    # Load multiple seasons
    uv run python scripts/populate_plays.py --start-season 2020 --end-season 2024

    # Load with all data (FTN + snap counts)
    uv run python scripts/populate_plays.py --start-season 2022 --end-season 2024 --include-all

    # Update current season with new games
    uv run python scripts/populate_plays.py --update

    # Run migration only (setup schema)
    uv run python scripts/populate_plays.py --migrate-only
"""

import argparse
import sys
import logging
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ffpy.nflverse_loader import NFLVerseLoader, setup_database
from ffpy.database import FFPyDatabase
from ffpy.config import Config


def setup_logging(verbose: bool = True):
    """Configure logging."""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Populate FFPy database with NFL play-by-play data from nflverse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Action arguments
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="Only run database migration (setup schema), don't load data",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update current season with new games only (incremental)",
    )

    # Season selection
    parser.add_argument(
        "--season",
        type=int,
        help="Single season to load (e.g., 2024)",
    )
    parser.add_argument(
        "--start-season",
        type=int,
        help="Start season for range load (e.g., 2020)",
    )
    parser.add_argument(
        "--end-season",
        type=int,
        help="End season for range load (defaults to current NFL season)",
    )

    # Data options
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include FTN charting and snap counts (default: True)",
        default=True,
    )
    parser.add_argument(
        "--no-ftn",
        action="store_true",
        help="Skip FTN charting data (only available 2022+)",
    )
    parser.add_argument(
        "--no-snaps",
        action="store_true",
        help="Skip snap count data (only available 2012+)",
    )

    # Database options
    parser.add_argument(
        "--db-path",
        type=str,
        help=f"Custom database path (default: {Config.DATABASE_PATH})",
    )

    # Output options
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run data quality validation after load",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(not args.quiet)

    # Validate arguments
    if not args.migrate_only and not args.update and not args.season and not args.start_season:
        parser.error("Must specify --season, --start-season, --update, or --migrate-only")

    if args.season and args.start_season:
        parser.error("Cannot specify both --season and --start-season")

    # Initialize database
    print("\nInitializing database...")
    db = setup_database(args.db_path)
    print(f"Database: {db.db_path}\n")

    # Migrate only mode
    if args.migrate_only:
        print("Migration complete! Schema is ready.")
        print("\nNext steps:")
        print("  1. Load a single season: python scripts/populate_plays.py --season 2024")
        print(
            "  2. Load multiple seasons: python scripts/populate_plays.py --start-season 2020 --end-season 2024"
        )
        return

    # Create loader
    loader = NFLVerseLoader(db)

    try:
        # Update mode
        if args.update:
            print(f"Updating current season ({Config.NFL_SEASON})...\n")
            stats = loader.update_current_season(verbose=not args.quiet)

            if stats["plays"] == 0:
                print("\nAlready up to date!")
            else:
                print(f"\nUpdate complete: {stats['plays']} new plays added")

        # Single season mode
        elif args.season:
            print(f"Loading {args.season} season...\n")
            stats = loader.load_season(
                season=args.season,
                include_ftn=not args.no_ftn,
                include_snaps=not args.no_snaps,
                verbose=not args.quiet,
            )

            if args.validate:
                print("\nValidating data quality...")
                validation = loader.validate_data_quality(args.season)
                print(f"Quality Score: {validation['quality_score']:.1f}%")
                print(f"  Total Plays: {validation['total_plays']}")
                print(f"  Total Games: {validation['total_games']}")
                if validation["missing_player_ids"] > 0:
                    print(f"  Missing Player IDs: {validation['missing_player_ids']}")
                if validation["missing_epa"] > 0:
                    print(f"  Missing EPA: {validation['missing_epa']}")

        # Multi-season mode
        else:
            end_season = args.end_season or Config.NFL_SEASON
            stats = loader.load_historical(
                start_season=args.start_season,
                end_season=end_season,
                include_ftn=not args.no_ftn,
                include_snaps=not args.no_snaps,
                verbose=not args.quiet,
            )

        # Print summary
        print("\n" + "=" * 60)
        print("Database populated successfully!")
        print(f"Database location: {db.db_path}")
        print("=" * 60)

        # Print usage examples
        print("\nNext steps - Query the data:")
        print("  1. Python REPL:")
        print("     >>> from ffpy.database import FFPyDatabase")
        print("     >>> db = FFPyDatabase()")
        print("     >>> plays = db.get_plays(season=2024, week=1)")
        print("")
        print("  2. Run analysis notebooks in examples/")
        print("")
        print("  3. Explore via Streamlit app (coming soon!)")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
