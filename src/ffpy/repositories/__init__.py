"""Repository adapters for historical pick'em data."""

from ffpy.repositories.base import HistoricalGamesRepository
from ffpy.repositories.sqlite_games import SQLiteHistoricalGamesRepository

__all__ = ["HistoricalGamesRepository", "SQLiteHistoricalGamesRepository"]
