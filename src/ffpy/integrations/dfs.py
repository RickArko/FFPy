"""DFS salary fetchers for DraftKings and FanDuel.

This module provides methods to scrape or fetch weekly DFS salaries
from major platforms. Production usage would use a paid API (e.g.,
Rotogrinders, FantasyPros) or web scraping.

The stub methods return empty DataFrames and serve as integration
points for future implementation.
"""

from typing import Optional

import pandas as pd


def fetch_draftkings_salaries(
    season: int,
    week: int,
) -> pd.DataFrame:
    """Fetch DraftKings weekly salaries.

    Args:
        season: NFL season year
        week: Week number (1-18)

    Returns:
        DataFrame with columns: player_name, salary, position, team, opponent
    """
    # TODO: Implement DraftKings salary fetch via API or scraping.
    # Columns: player_name (str), salary (int), position (str),
    #          team (str), opponent (str)
    return pd.DataFrame()


def fetch_fanduel_salaries(
    season: int,
    week: int,
) -> pd.DataFrame:
    """Fetch FanDuel weekly salaries.

    Args:
        season: NFL season year
        week: Week number (1-18)

    Returns:
        DataFrame with columns: player_name, salary, position, team, opponent
    """
    # TODO: Implement FanDuel salary fetch via API or scraping.
    return pd.DataFrame()


def fetch_all_platforms(
    season: int,
    week: int,
    platforms: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Fetch DFS salaries from all configured platforms.

    Args:
        season: NFL season year
        week: Week number (1-18)
        platforms: List of platforms to fetch (default: all)

    Returns:
        Dict mapping platform name -> DataFrame of salaries
    """
    if platforms is None:
        platforms = ["draftkings", "fanduel"]

    results: dict[str, pd.DataFrame] = {}
    fetchers = {
        "draftkings": fetch_draftkings_salaries,
        "fanduel": fetch_fanduel_salaries,
    }

    for platform in platforms:
        if platform in fetchers:
            results[platform] = fetchers[platform](season, week)

    return results
