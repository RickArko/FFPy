"""ADP (Average Draft Position) fetchers for various platforms.

Provides methods to fetch ADP data from FantasyPros, Underdog, and
other platforms. The stub methods return empty DataFrames and serve
as integration points for future implementation.
"""

from typing import Optional

import pandas as pd


def fetch_fantasypros_adp(season: int) -> pd.DataFrame:
    """Fetch ADP data from FantasyPros.

    Args:
        season: NFL season year

    Returns:
        DataFrame with columns: player_name, position, platform,
                                adp, adp_high, adp_low, draft_date
    """
    # TODO: Implement FantasyPros ADP fetch.
    # player_name (str), position (str), platform='fantasypros',
    # adp (float), adp_high (float), adp_low (float), draft_date (str)
    return pd.DataFrame()


def fetch_underdog_adp(season: int) -> pd.DataFrame:
    """Fetch ADP data from Underdog Fantasy.

    Args:
        season: NFL season year

    Returns:
        DataFrame with columns: player_name, position, platform,
                                adp, adp_high, adp_low, draft_date
    """
    # TODO: Implement Underdog ADP fetch.
    return pd.DataFrame()


def fetch_all_platforms(
    season: int,
    platforms: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Fetch ADP from all configured platforms.

    Args:
        season: NFL season year
        platforms: List of platforms (default: all)

    Returns:
        Dict mapping platform name -> DataFrame of ADP data
    """
    if platforms is None:
        platforms = ["fantasypros", "underdog"]

    results: dict[str, pd.DataFrame] = {}
    fetchers = {
        "fantasypros": fetch_fantasypros_adp,
        "underdog": fetch_underdog_adp,
    }

    for platform in platforms:
        if platform in fetchers:
            results[platform] = fetchers[platform](season)

    return results
