"""Repository protocols for historical pick'em data."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class HistoricalGamesRepository(Protocol):
    """Read-only access pattern required by the pick'em backtester."""

    def get_historical_games(
        self,
        season: int,
        week: Optional[int] = None,
        season_type: str = "REG",
        finished_only: bool = True,
    ) -> pd.DataFrame: ...

    def get_data_coverage(
        self,
        season_start: Optional[int] = None,
        season_end: Optional[int] = None,
        season_type: str = "REG",
    ) -> pd.DataFrame: ...
