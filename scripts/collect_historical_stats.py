"""
Collect historical actual stats from ESPN and populate database.

Usage:
    uv run python scripts/collect_historical_stats.py --season 2024 --weeks 1-17
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ffpy.database import FFPyDatabase
from ffpy.integrations import ESPNIntegration
import argparse
import time


def collect_stats(season: int, start_week: int, end_week: int):
    """
    Collect historical actual stats for a season.

    Args:
        season: NFL season year (e.g., 2024)
        start_week: Starting week number
        end_week: Ending week number
    """
    print(f"\n=== Collecting Historical Stats for {season} Season ===")
    print(f"Weeks {start_week} to {end_week}\n")

    # Initialize database and ESPN integration
    db = FFPyDatabase()
    espn = ESPNIntegration()

    total_weeks = end_week - start_week + 1
    total_players = 0

    for week in range(start_week, end_week + 1):
        print(f"[Week {week}/{end_week}] Fetching data...")

        # Check if we already have this data
        if db.check_api_request("espn", season, week, "actuals"):
            print(f"  [OK] Week {week} already collected, skipping")
            continue

        try:
            # Fetch actual stats from ESPN
            df = espn.get_actual_stats(week=week, season=season)

            if df.empty:
                print(f"  [WARN] No data returned for week {week}")
                db.log_api_request(
                    "espn", season, week, "actuals", False, "No data returned"
                )
                continue

            # Store in database
            db.store_actual_stats(df, season=season, week=week, source="espn")

            # Log successful request
            db.log_api_request("espn", season, week, "actuals", True)

            players_count = len(df)
            total_players += players_count

            print(f"  [OK] Stored {players_count} players")

            # Be nice to ESPN's servers (wait 1 second between requests)
            if week < end_week:
                time.sleep(1)

        except Exception as e:
            print(f"  [ERROR] {e}")
            db.log_api_request("espn", season, week, "actuals", False, str(e))
            continue

    print(f"\n=== Collection Complete ===")
    print(f"Total weeks processed: {total_weeks}")
    print(f"Total players stored: {total_players}")
    print(f"Database location: {db.db_path}")

    # Show sample data
    print(f"\n=== Sample Data (Week {start_week}, QB) ===")
    sample = db.get_actual_stats(season=season, week=start_week, position="QB")
    if not sample.empty:
        print(
            sample[["player", "team", "actual_points", "passing_yards", "passing_tds"]]
            .head(10)
            .to_string(index=False)
        )

    db.close()


def main():
    parser = argparse.ArgumentParser(description="Collect historical NFL fantasy stats")
    parser.add_argument("--season", type=int, default=2024, help="NFL season year")
    parser.add_argument("--start-week", type=int, default=1, help="Starting week")
    parser.add_argument(
        "--end-week", type=int, default=17, help="Ending week (17 for regular season)"
    )

    args = parser.parse_args()

    collect_stats(args.season, args.start_week, args.end_week)


if __name__ == "__main__":
    main()
