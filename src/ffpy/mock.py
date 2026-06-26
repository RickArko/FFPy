"""Generate realistic mock NFL fantasy data for development and demos.

Useful when you don't want to hit real nflverse/ESPN endpoints (rate limits,
offline, CI) but still want the app and notebooks to render meaningful numbers.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

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


NFL_TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LAC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
]

_ROOFS = ["outdoors", "dome", "open", "closed"]
_SURFACES = ["grass", "fieldturf", "matrixturf"]


def generate_season_data(
    season: int = 2024,
    weeks: int = 17,
    db_path: str | None = None,
    start_week: int = 1,
) -> int:
    """Populate the database with mock stats for a full season.

    Returns the number of rows inserted.
    """
    print(f"Generating mock {season} season data (weeks {start_week}-{weeks})...")

    db = FFPyDatabase(db_path=db_path)
    total = 0
    try:
        for week in range(start_week, weeks + 1):
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


def _first_sunday_in_september(season: int) -> date:
    september_first = date(season, 9, 1)
    days_until_sunday = (6 - september_first.weekday()) % 7
    return september_first + timedelta(days=days_until_sunday)


def _mock_game_row(
    *,
    rng: random.Random,
    season: int,
    week: int,
    game_index: int,
    home_team: str,
    away_team: str,
    game_date: date,
) -> dict:
    spread_line = rng.choice([x * 0.5 for x in range(-20, 21)])
    total_line = rng.choice([x * 0.5 for x in range(76, 113)])
    expected_total = int(round(total_line + rng.gauss(0, 5)))
    home_margin = int(round(spread_line + rng.gauss(0, 10)))

    home_score = max(3, int(round((expected_total + home_margin) / 2)))
    away_score = max(3, expected_total - home_score)

    return {
        "game_id": f"{season}_{week:02d}_{away_team}_{home_team}",
        "old_game_id": f"{season}{week:02d}{game_index:02d}",
        "season": season,
        "season_type": "REG",
        "week": week,
        "game_date": game_date.isoformat(),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "roof": rng.choice(_ROOFS),
        "surface": rng.choice(_SURFACES),
        "temp": rng.randint(35, 85),
        "wind": rng.randint(0, 18),
        "spread_line": spread_line,
        "total_line": total_line,
        "location": "Home",
        "stadium": f"{home_team} Stadium",
    }


def generate_pickem_game_data(
    season: int = 2024,
    weeks: int = 17,
    db_path: str | None = None,
    start_week: int = 1,
    seed: int | None = 2024,
) -> int:
    """Populate the database with mock completed games for pick'em backtests.

    Returns the number of game rows upserted.
    """
    print(f"Generating mock {season} pick'em game data (weeks {start_week}-{weeks})...")

    rng = random.Random(seed)
    regular_season_start = _first_sunday_in_september(season)
    rows = []

    for week in range(start_week, weeks + 1):
        teams = NFL_TEAMS.copy()
        rng.shuffle(teams)
        game_date = regular_season_start + timedelta(days=(week - 1) * 7)

        for game_index, offset in enumerate(range(0, len(teams), 2), start=1):
            away_team = teams[offset]
            home_team = teams[offset + 1]
            rows.append(
                _mock_game_row(
                    rng=rng,
                    season=season,
                    week=week,
                    game_index=game_index,
                    home_team=home_team,
                    away_team=away_team,
                    game_date=game_date,
                )
            )

    db = FFPyDatabase(db_path=db_path)
    try:
        db.run_migration("002_play_by_play_schema.sql")
        inserted = db.store_games(pd.DataFrame(rows))
        print(f"\nDone. Upserted {inserted} mock games at {db.db_path}")
        return inserted
    finally:
        db.close()
