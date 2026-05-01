"""SQLite-backed repository adapter for historical pick'em data."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from ffpy.database import FFPyDatabase


class SQLiteHistoricalGamesRepository:
    """Small adapter that exposes just the backtester's read API."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    @property
    def conn(self):
        """Expose the underlying connection for legacy backtest persistence."""
        return self.db.conn

    def close(self) -> None:
        """Close the wrapped database handle."""
        self.db.close()

    def get_historical_games(
        self,
        season: int,
        week: Optional[int] = None,
        season_type: str = "REG",
        finished_only: bool = True,
    ) -> pd.DataFrame:
        return self.db.get_historical_games(
            season=season,
            week=week,
            season_type=season_type,
            finished_only=finished_only,
        )

    def get_data_coverage(
        self,
        season_start: Optional[int] = None,
        season_end: Optional[int] = None,
        season_type: str = "REG",
    ) -> pd.DataFrame:
        return self.db.get_data_coverage(
            season_start=season_start,
            season_end=season_end,
            season_type=season_type,
        )
