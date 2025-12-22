"""
Generate realistic mock 2024 NFL season data for demonstration.

This creates actual player stats that look realistic so we can demonstrate
the database and projection system while ESPN API is blocked.

Usage:
    uv run python scripts/generate_mock_2024_data.py
"""

import sys
from pathlib import Path
import random
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ffpy.database import FFPyDatabase


# Top players by position (2024 season leaders)
TOP_PLAYERS = {
    "QB": [
        ("Lamar Jackson", "BAL"),
        ("Josh Allen", "BUF"),
        ("Jalen Hurts", "PHI"),
        ("Dak Prescott", "DAL"),
        ("Patrick Mahomes", "KC"),
        ("Joe Burrow", "CIN"),
        ("CJ Stroud", "HOU"),
        ("Brock Purdy", "SF"),
        ("Jordan Love", "GB"),
        ("Jared Goff", "DET"),
    ],
    "RB": [
        ("Christian McCaffrey", "SF"),
        ("Derrick Henry", "BAL"),
        ("Bijan Robinson", "ATL"),
        ("Breece Hall", "NYJ"),
        ("Saquon Barkley", "PHI"),
        ("Jahmyr Gibbs", "DET"),
        ("De Von Achane", "MIA"),
        ("Kyren Williams", "LAR"),
        ("Jonathan Taylor", "IND"),
        ("Josh Jacobs", "GB"),
    ],
    "WR": [
        ("CeeDee Lamb", "DAL"),
        ("Tyreek Hill", "MIA"),
        ("Amon-Ra St. Brown", "DET"),
        ("Justin Jefferson", "MIN"),
        ("AJ Brown", "PHI"),
        ("Nico Collins", "HOU"),
        ("Puka Nacua", "LAR"),
        ("Ja Marr Chase", "CIN"),
        ("Brandon Aiyuk", "SF"),
        ("Garrett Wilson", "NYJ"),
    ],
    "TE": [
        ("Travis Kelce", "KC"),
        ("Sam LaPorta", "DET"),
        ("George Kittle", "SF"),
        ("Mark Andrews", "BAL"),
        ("Trey McBride", "ARI"),
        ("Evan Engram", "JAC"),
        ("TJ Hockenson", "MIN"),
        ("Dalton Kincaid", "BUF"),
        ("David Njoku", "CLE"),
        ("Kyle Pitts", "ATL"),
    ],
}


def generate_qb_stats(player_name: str, week: int) -> dict:
    """Generate realistic QB stats with some variance."""
    base_points = random.uniform(15, 28)
    variance = random.uniform(0.8, 1.2)

    return {
        "passing_yards": int(random.uniform(220, 320) * variance),
        "passing_tds": round(random.uniform(1.5, 3.0) * variance, 1),
        "interceptions": int(random.uniform(0, 2)),
        "rushing_yards": int(random.uniform(10, 50) * variance),
        "rushing_tds": round(random.uniform(0, 0.5) * variance, 1),
        "actual_points": round(base_points * variance, 1),
    }


def generate_rb_stats(player_name: str, week: int) -> dict:
    """Generate realistic RB stats with some variance."""
    base_points = random.uniform(10, 22)
    variance = random.uniform(0.7, 1.3)

    return {
        "rushing_yards": int(random.uniform(60, 120) * variance),
        "rushing_tds": round(random.uniform(0.3, 1.2) * variance, 1),
        "receiving_yards": int(random.uniform(15, 60) * variance),
        "receiving_tds": round(random.uniform(0, 0.4) * variance, 1),
        "receptions": int(random.uniform(2, 6) * variance),
        "actual_points": round(base_points * variance, 1),
    }


def generate_wr_stats(player_name: str, week: int) -> dict:
    """Generate realistic WR stats with some variance."""
    base_points = random.uniform(8, 20)
    variance = random.uniform(0.7, 1.3)

    return {
        "rushing_yards": int(random.uniform(0, 10)),
        "rushing_tds": 0,
        "receiving_yards": int(random.uniform(50, 110) * variance),
        "receiving_tds": round(random.uniform(0.2, 1.0) * variance, 1),
        "receptions": int(random.uniform(4, 9) * variance),
        "actual_points": round(base_points * variance, 1),
    }


def generate_te_stats(player_name: str, week: int) -> dict:
    """Generate realistic TE stats with some variance."""
    base_points = random.uniform(6, 15)
    variance = random.uniform(0.7, 1.3)

    return {
        "rushing_yards": 0,
        "rushing_tds": 0,
        "receiving_yards": int(random.uniform(35, 80) * variance),
        "receiving_tds": round(random.uniform(0.2, 0.8) * variance, 1),
        "receptions": int(random.uniform(3, 7) * variance),
        "actual_points": round(base_points * variance, 1),
    }


def generate_season_data(season: int = 2024, weeks: int = 17):
    """Generate full season of mock data."""
    print(f"\n=== Generating Mock {season} Season Data ===")
    print(f"Weeks 1-{weeks}\n")

    db = FFPyDatabase()
    total_records = 0

    stat_generators = {
        "QB": generate_qb_stats,
        "RB": generate_rb_stats,
        "WR": generate_wr_stats,
        "TE": generate_te_stats,
    }

    for week in range(1, weeks + 1):
        print(f"Generating Week {week}...")

        week_data = []

        for position, players in TOP_PLAYERS.items():
            for player_name, team in players:
                # Generate stats for this player/week
                stats = stat_generators[position](player_name, week)

                week_data.append(
                    {
                        "player": player_name,
                        "team": team,
                        "position": position,
                        "opponent": "OPP",  # Simplified
                        **stats,
                    }
                )

        # Store in database
        df = pd.DataFrame(week_data)
        db.store_actual_stats(df, season=season, week=week, source="mock")
        db.log_api_request("mock", season, week, "actuals", True)

        total_records += len(df)
        print(f"  Stored {len(df)} players")

    print(f"\n=== Generation Complete ===")
    print(f"Total records: {total_records}")
    print(f"Database: {db.db_path}")

    # Show sample
    print(f"\n=== Sample Data (Week 1, Top 5 QB) ===")
    sample = db.get_actual_stats(season=season, week=1, position="QB")
    if not sample.empty:
        print(
            sample[["player", "team", "actual_points", "passing_yards", "passing_tds"]]
            .head(5)
            .to_string(index=False)
        )

    db.close()


if __name__ == "__main__":
    generate_season_data()
