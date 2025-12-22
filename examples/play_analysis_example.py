"""
Example script demonstrating play-by-play data analysis.

This script shows common queries and analyses using the play-by-play database.

Usage:
    uv run python examples/play_analysis_example.py
"""

from ffpy.database import FFPyDatabase
import pandas as pd


def main():
    """Run example analyses."""
    print("\n" + "=" * 60)
    print("FFPy Play-by-Play Data Analysis Examples")
    print("=" * 60 + "\n")

    # Initialize database
    with FFPyDatabase() as db:
        # Example 1: Get all touchdowns for a player
        print("Example 1: Player Touchdowns")
        print("-" * 60)

        # Get touchdowns for a specific player (adjust name as needed)
        player_name = "P.Mahomes"
        season = 2024

        query = """
            SELECT game_date, week, desc, yards_gained, epa
            FROM plays
            WHERE passer_player_name = ?
                AND pass_touchdown = 1
                AND season = ?
            ORDER BY game_date
        """

        touchdowns = pd.read_sql(query, db.conn, params=[player_name, season])

        if not touchdowns.empty:
            print(f"\n{player_name} touchdown passes in {season}:")
            print(touchdowns.to_string(index=False))
            print(f"\nTotal TD passes: {len(touchdowns)}")
        else:
            print(f"\nNo data found for {player_name} in {season}")
            print("Try loading data first: python scripts/populate_plays.py --season 2024")

        # Example 2: Red zone efficiency for a team
        print("\n\nExample 2: Team Red Zone Efficiency")
        print("-" * 60)

        team = "KC"

        query = """
            SELECT
                COUNT(*) as plays,
                SUM(CASE WHEN touchdown = 1 THEN 1 ELSE 0 END) as tds,
                ROUND(100.0 * SUM(touchdown) / COUNT(*), 1) as td_rate,
                ROUND(AVG(epa), 3) as avg_epa
            FROM plays
            WHERE posteam = ?
                AND yardline_100 <= 20
                AND season = ?
                AND play_type IN ('pass', 'run')
        """

        red_zone = pd.read_sql(query, db.conn, params=[team, season])

        if not red_zone.empty and red_zone["plays"].iloc[0] > 0:
            print(f"\n{team} red zone stats in {season}:")
            print(f"  Plays: {red_zone['plays'].iloc[0]}")
            print(f"  TDs: {red_zone['tds'].iloc[0]}")
            print(f"  TD Rate: {red_zone['td_rate'].iloc[0]}%")
            print(f"  Avg EPA: {red_zone['avg_epa'].iloc[0]}")
        else:
            print(f"\nNo red zone data found for {team} in {season}")

        # Example 3: Receiver target share
        print("\n\nExample 3: Receiver Target Share")
        print("-" * 60)

        receiver_name = "T.Kelce"

        # Calculate target share using database method
        target_share = db.calculate_target_share(receiver_name, season)

        if target_share > 0:
            print(f"\n{receiver_name} target share in {season}:")
            print(f"  {target_share:.1%} of team targets")

            # Get detailed targets
            targets = db.get_player_targets(receiver_name, season)

            if not targets.empty:
                print(f"  Total targets: {len(targets)}")
                print(f"  Completions: {targets['complete_pass'].sum()}")
                print(f"  Total yards: {targets['yards_gained'].sum()}")
                print(f"  Avg air yards: {targets['air_yards'].mean():.1f}")
                print(f"  TDs: {targets['touchdown'].sum()}")
        else:
            print(f"\nNo target data found for {receiver_name} in {season}")

        # Example 4: Player EPA trends
        print("\n\nExample 4: Player EPA Trends")
        print("-" * 60)

        qb_name = "P.Mahomes"

        # Get weekly EPA
        query = """
            SELECT
                week,
                COUNT(*) as dropbacks,
                ROUND(AVG(epa), 3) as avg_epa,
                ROUND(SUM(epa), 2) as total_epa,
                SUM(complete_pass) as completions,
                SUM(pass_touchdown) as tds
            FROM plays
            WHERE passer_player_name = ?
                AND season = ?
                AND qb_dropback = 1
            GROUP BY week
            ORDER BY week
        """

        weekly_epa = pd.read_sql(query, db.conn, params=[qb_name, season])

        if not weekly_epa.empty:
            print(f"\n{qb_name} weekly EPA in {season}:")
            print(weekly_epa.to_string(index=False))
            print(f"\nSeason Avg EPA/play: {weekly_epa['avg_epa'].mean():.3f}")
        else:
            print(f"\nNo EPA data found for {qb_name} in {season}")

        # Example 5: Database statistics
        print("\n\nExample 5: Database Statistics")
        print("-" * 60)

        # Count total records
        plays_count = pd.read_sql("SELECT COUNT(*) as count FROM plays", db.conn)
        games_count = pd.read_sql("SELECT COUNT(*) as count FROM games", db.conn)

        print(f"\nDatabase statistics:")
        print(f"  Total plays: {plays_count['count'].iloc[0]:,}")
        print(f"  Total games: {games_count['count'].iloc[0]:,}")

        # Get seasons available
        seasons_query = """
            SELECT DISTINCT season
            FROM plays
            ORDER BY season DESC
        """
        seasons = pd.read_sql(seasons_query, db.conn)

        if not seasons.empty:
            print(f"  Available seasons: {', '.join(map(str, seasons['season'].tolist()))}")

    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
