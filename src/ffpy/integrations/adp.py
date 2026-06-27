"""ADP and ECR fetchers using nflreadpy.

Uses ``nflreadpy.load_ff_rankings()`` to fetch expert consensus rankings
from FantasyPros, which serves as a reliable ADP proxy.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

try:
    import nflreadpy as nfl
except ImportError:
    nfl = None


def _rankings_to_adp(raw: pd.DataFrame, platform: str) -> pd.DataFrame:
    """Convert FantasyPros ECR rankings to our ADP schema.

    Args:
        raw: DataFrame from load_ff_rankings()
        platform: Platform label to assign

    Returns:
        DataFrame with columns: player_name, position, platform,
        adp, adp_high, adp_low, team
    """
    if raw.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["player_name"] = raw.get("player", None)
    out["position"] = raw.get("pos", None)
    out["team"] = raw.get("team", None)
    out["platform"] = platform
    out["adp"] = raw.get("ecr", None)
    out["adp_high"] = raw.get("best", None)  # best rank
    out["adp_low"] = raw.get("worst", None)  # worst rank

    return out.dropna(subset=["player_name"]).reset_index(drop=True)


def fetch_draft_rankings(season: int) -> pd.DataFrame:
    """Fetch draft-season expert consensus rankings via nflreadpy.

    Args:
        season: NFL season year

    Returns:
        DataFrame with ranking data across all positions.
    """
    if nfl is None:
        return pd.DataFrame()

    try:
        raw = nfl.load_ff_rankings(type="draft")
        if raw.is_empty():
            return pd.DataFrame()
        pdf = raw.to_pandas()

        # Filter to standard position player rankings (not DST, dynasty, etc.)
        valid_page_types = [
            "best-overall", "best-qb", "best-rb", "best-wr", "best-te",
        ]
        pdf = pdf[pdf["page_type"].isin(valid_page_types)].copy()
        return pdf
    except Exception:
        return pd.DataFrame()


def fetch_fantasypros_adp(season: int) -> pd.DataFrame:
    """Fetch ADP data from FantasyPros via nflreadpy ECR.

    Args:
        season: NFL season year

    Returns:
        DataFrame with columns: player_name, position, platform,
                                adp, adp_high, adp_low, team
    """
    pdf = fetch_draft_rankings(season)
    return _rankings_to_adp(pdf, "fantasypros")


def fetch_underdog_adp(season: int) -> pd.DataFrame:
    """Fetch ADP-style data using ECR as a proxy for Underdog.

    Args:
        season: NFL season year

    Returns:
        DataFrame with ADP data
    """
    pdf = fetch_draft_rankings(season)
    return _rankings_to_adp(pdf, "underdog")


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
