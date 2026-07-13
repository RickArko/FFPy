"""Persist Sleeper league imports for the standalone app."""

from __future__ import annotations

from ffpy.database import FFPyDatabase
from ffpy.sleeper_import import import_from_sleeper


class SleeperImportService:
    """Thin wrapper around shared import logic and database storage."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def import_league(
        self,
        user_id: str,
        sleeper_league_id: str,
        season: int,
        *,
        franchise_id: str | None = None,
    ) -> str:
        data = import_from_sleeper(sleeper_league_id, season)
        data["league"]["franchise_id"] = franchise_id
        return self.db.store_user_league(user_id, data, franchise_id=franchise_id)


__all__ = ["SleeperImportService"]
