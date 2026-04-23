"""Generate realistic mock NFL fantasy data for development and demos.

Useful when you don't want to hit real nflverse/ESPN endpoints (rate limits,
offline, CI) but still want the app and notebooks to render meaningful numbers.
"""

from __future__ import annotations

import random

import pandas as pd

from ffpy.database import FFPyDatabase

TOP_PLAYERS: dict[str, list[tuple[str, str]]] = {
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


def _qb_stats() -> dict:
    variance = random.uniform(0.8, 1.2)
    return {
        "passing_yards": int(random.uniform(220, 320) * variance),
        "passing_tds": round(random.uniform(1.5, 3.0) * variance, 1),
        "interceptions": int(random.uniform(0, 2)),
        "rushing_yards": int(random.uniform(10, 50) * variance),
        "rushing_tds": round(random.uniform(0, 0.5) * variance, 1),
        "actual_points": round(random.uniform(15, 28) * variance, 1),
    }


def _rb_stats() -> dict:
    variance = random.uniform(0.7, 1.3)
    return {
        "rushing_yards": int(random.uniform(60, 120) * variance),
        "rushing_tds": round(random.uniform(0.3, 1.2) * variance, 1),
        "receiving_yards": int(random.uniform(15, 60) * variance),
        "receiving_tds": round(random.uniform(0, 0.4) * variance, 1),
        "receptions": int(random.uniform(2, 6) * variance),
        "actual_points": round(random.uniform(10, 22) * variance, 1),
    }


def _wr_stats() -> dict:
    variance = random.uniform(0.7, 1.3)
    return {
        "rushing_yards": int(random.uniform(0, 10)),
        "rushing_tds": 0,
        "receiving_yards": int(random.uniform(50, 110) * variance),
        "receiving_tds": round(random.uniform(0.2, 1.0) * variance, 1),
        "receptions": int(random.uniform(4, 9) * variance),
        "actual_points": round(random.uniform(8, 20) * variance, 1),
    }


def _te_stats() -> dict:
    variance = random.uniform(0.7, 1.3)
    return {
        "rushing_yards": 0,
        "rushing_tds": 0,
        "receiving_yards": int(random.uniform(35, 80) * variance),
        "receiving_tds": round(random.uniform(0.2, 0.8) * variance, 1),
        "receptions": int(random.uniform(3, 7) * variance),
        "actual_points": round(random.uniform(6, 15) * variance, 1),
    }


_STAT_GENERATORS = {"QB": _qb_stats, "RB": _rb_stats, "WR": _wr_stats, "TE": _te_stats}


def generate_season_data(season: int = 2024, weeks: int = 17) -> int:
    """Populate the database with mock stats for a full season.

    Returns the number of rows inserted.
    """
    print(f"Generating mock {season} season data (weeks 1-{weeks})...")

    db = FFPyDatabase()
    total = 0
    try:
        for week in range(1, weeks + 1):
            print(f"  week {week}... ", end="", flush=True)
            rows = []
            for position, players in TOP_PLAYERS.items():
                generator = _STAT_GENERATORS[position]
                for player_name, team in players:
                    rows.append(
                        {
                            "player": player_name,
                            "team": team,
                            "position": position,
                            "opponent": "OPP",
                            **generator(),
                        }
                    )
            df = pd.DataFrame(rows)
            db.store_actual_stats(df, season=season, week=week, source="mock")
            db.log_api_request("mock", season, week, "actuals", True)
            total += len(df)
            print(f"{len(df)} rows")

        print(f"\nDone. Inserted {total} mock records at {db.db_path}")
        return total
    finally:
        db.close()
