"""Pre-season rookie fantasy projections for the draft strategy engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase

BACKTEST_SEASONS = [2022, 2023, 2024]

# Positional projection curve: PPG by within-position ADP rank (matches draft_strategy).
_CURVE: Dict[str, Tuple[float, float, int]] = {
    "QB": (22.0, 11.0, 22),
    "RB": (17.5, 5.0, 48),
    "WR": (16.5, 5.0, 55),
    "TE": (12.5, 3.5, 22),
    "K": (9.0, 6.0, 20),
    "DST": (9.0, 5.0, 20),
}

# Fallback round medians when DB backtest data is sparse.
_FALLBACK_ROUND_MEDIANS: Dict[Tuple[str, int], float] = {
    ("RB", 1): 19.5,
    ("RB", 2): 12.0,
    ("RB", 3): 9.0,
    ("RB", 4): 7.5,
    ("WR", 1): 14.5,
    ("WR", 2): 11.0,
    ("WR", 3): 8.5,
    ("TE", 1): 11.0,
    ("TE", 2): 7.5,
    ("QB", 1): 18.0,
    ("QB", 2): 15.0,
}

_POSITION_STD: Dict[str, float] = {
    "QB": 8.0,
    "RB": 10.0,
    "WR": 9.0,
    "TE": 8.0,
    "K": 4.0,
    "DST": 5.0,
}


@dataclass
class RookieProjection:
    ppg: float
    std: float
    floor_ppg: float
    ceiling_ppg: float


def market_curve_ppg(position: str, pos_rank: int) -> float:
    top, floor, span = _CURVE.get(position, (10.0, 4.0, 40))
    return max(floor, top - (top - floor) * (pos_rank - 1) / max(1, span))


def _load_rookie_outcomes(db: FFPyDatabase, seasons: List[int]) -> pd.DataFrame:
    if not seasons:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in seasons)
    query = f"""
        SELECT pr.player_name, pr.position, pr.season, pr.draft_round, pr.draft_pick,
               COUNT(a.actual_points) AS weeks,
               AVG(a.actual_points) AS ppg
        FROM player_rosters pr
        JOIN players p ON p.name = pr.player_name
        JOIN actual_stats a ON a.player_id = p.player_id AND a.season = pr.season
        WHERE pr.season IN ({placeholders})
          AND pr.draft_round IS NOT NULL
          AND pr.years_exp <= 1
        GROUP BY pr.player_name, pr.position, pr.season, pr.draft_round, pr.draft_pick
        HAVING weeks >= 8
    """
    try:
        return pd.read_sql(query, db.conn, params=seasons)
    except Exception:
        return pd.DataFrame()


def draft_capital_ppg(
    db: FFPyDatabase,
    position: str,
    draft_round: Optional[int],
    *,
    history: Optional[pd.DataFrame] = None,
) -> Optional[float]:
    if draft_round is None:
        return None
    fallback = _FALLBACK_ROUND_MEDIANS.get((position, draft_round))
    if history is None:
        history = _load_rookie_outcomes(db, BACKTEST_SEASONS)
    if history.empty:
        return fallback
    hit = history[(history["position"] == position) & (history["draft_round"] == draft_round)]
    if not hit.empty:
        return float(hit["ppg"].median())
    pos_rows = history[history["position"] == position]
    if not pos_rows.empty:
        return float(pos_rows["ppg"].median())
    return fallback


def adp_rank_proxy_ppg(
    db: FFPyDatabase,
    position: str,
    pos_rank: int,
    *,
    history: Optional[pd.DataFrame] = None,
) -> Optional[float]:
    if history is None:
        history = _load_rookie_outcomes(db, BACKTEST_SEASONS)
    if history.empty:
        return None
    sub = history[history["position"] == position].copy()
    if sub.empty:
        return None
    sub["draft_rank_pos"] = sub.groupby(["season", "position"])["draft_pick"].rank(method="first")
    sub["rank_bucket"] = (sub["draft_rank_pos"] // 2) * 2
    med = sub.groupby("rank_bucket")["ppg"].median()
    bucket = max(2, (pos_rank // 2) * 2)
    if bucket in med.index:
        return float(med.loc[bucket])
    return float(sub["ppg"].median())


def project(
    db: FFPyDatabase,
    *,
    name: str,
    position: str,
    adp_rank: int,
    pos_rank: int,
    season: int,
    curve_fn: Optional[Callable[[str, int], float]] = None,
    history: Optional[pd.DataFrame] = None,
    draft_capital: Optional[Dict[str, int]] = None,
) -> RookieProjection:
    """Blend market curve, draft capital, and ADP-rank proxy for a rookie."""
    curve = curve_fn or market_curve_ppg
    market = curve(position, pos_rank)
    if history is None:
        history = _load_rookie_outcomes(db, BACKTEST_SEASONS)

    if draft_capital is not None:
        draft_round = draft_capital.get("draft_round")
    else:
        dc = db.get_rookie_draft_capital(name, season)
        draft_round = dc["draft_round"] if dc else None
    capital = draft_capital_ppg(db, position, draft_round, history=history)
    proxy = adp_rank_proxy_ppg(db, position, pos_rank, history=history)

    if capital is not None:
        mean = 0.4 * market + 0.6 * capital
    elif proxy is not None and np.isfinite(proxy):
        mean = 0.4 * market + 0.6 * proxy
    else:
        mean = market

    std = _POSITION_STD.get(position, 10.0)
    if not history.empty:
        pos_std = history[history["position"] == position]["ppg"].std()
        if pos_std is not None and np.isfinite(pos_std) and pos_std > 0:
            std = float(pos_std)

    return RookieProjection(
        ppg=round(mean, 2),
        std=round(std, 2),
        floor_ppg=round(mean - std, 1),
        ceiling_ppg=round(mean + 1.28 * std, 1),
    )


__all__ = [
    "RookieProjection",
    "market_curve_ppg",
    "draft_capital_ppg",
    "adp_rank_proxy_ppg",
    "project",
]
