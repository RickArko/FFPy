"""Team depth chart fetchers.

Provides methods to fetch weekly depth charts, primarily via
nflreadpy's load_depth_charts(). The nflverse method is preferred
since the data is already available through nflreadpy.

If nflreadpy is unavailable or the user wants an alternative source,
the stub methods here can be extended.
"""

from typing import Optional

import pandas as pd

try:
    import nflreadpy as nfl
except ImportError:
    nfl = None  # type: ignore[assignment]


def fetch_nflverse_depth_charts(
    season: int,
    week: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch weekly depth charts via nflreadpy.

    Args:
        season: NFL season year
        week: Optional week filter (None = all weeks)

    Returns:
        DataFrame with columns: team, season, week, position,
                                player_name, depth_spot
    """
    if nfl is None:
        return pd.DataFrame()

    try:
        raw = nfl.load_depth_charts(seasons=[season])
    except Exception:
        return pd.DataFrame()

    if raw.is_empty():
        return pd.DataFrame()

    pdf = raw.to_pandas()
    out = pd.DataFrame()
    out["team"] = pdf.get("club_code", None)
    out["season"] = pdf.get("season", season)
    out["week"] = pdf.get("week", None)
    out["position"] = pdf.get("depth_position", None)
    out["player_name"] = pdf.get("full_name", None)
    out["depth_spot"] = pdf.get("depth_position", None)

    # Parse depth_spot from position string (e.g., "LWR1" -> 1)
    def _extract_depth(val):
        if val is None:
            return None
        digits = "".join(ch for ch in str(val) if ch.isdigit())
        return int(digits) if digits else None

    out["depth_spot"] = out.pop("depth_spot").apply(_extract_depth)

    out = out.dropna(subset=["player_name", "team", "week"]).reset_index(drop=True)
    out["week"] = out["week"].astype(int)
    out = out[out["week"].between(1, 22)].reset_index(drop=True)

    if week is not None:
        out = out[out["week"] == week].reset_index(drop=True)

    return out


def fetch_espn_depth_charts(
    season: int,
    week: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch depth charts from ESPN (fallback / alternative source).

    Args:
        season: NFL season year
        week: Optional week filter

    Returns:
        DataFrame with columns: team, season, week, position,
                                player_name, depth_spot
    """
    # TODO: Implement ESPN depth chart scraping.
    return pd.DataFrame()
