"""Sleeper franchise discovery via previous_league_id chains."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from ffpy.database import FFPyDatabase
from ffpy.integrations.sleeper import SleeperIntegration
from ffpy.sleeper_web.import_service import SleeperImportService

logger = logging.getLogger(__name__)


@dataclass
class FranchiseChain:
    """A multi-season Sleeper league lineage grouped by root ancestor."""

    root_league_id: str
    display_name: str
    leagues: List[dict] = field(default_factory=list)


class FranchiseService:
    """Discover, group, and import Sleeper franchise chains for a linked user."""

    def __init__(
        self,
        db: FFPyDatabase,
        *,
        import_service: Optional[SleeperImportService] = None,
        max_seasons: int = 10,
    ):
        self.db = db
        self.import_service = import_service or SleeperImportService(db)
        self.max_seasons = max_seasons

    def discover_chains(self, sleeper_user_id: str) -> List[FranchiseChain]:
        """Scan recent NFL seasons and group leagues by previous_league_id root."""
        current_year = datetime.now().year
        seen_league_ids: Set[str] = set()
        chains_by_root: Dict[str, FranchiseChain] = {}

        for offset in range(self.max_seasons + 1):
            season = current_year - offset
            try:
                season_leagues = SleeperIntegration.get_user_leagues(sleeper_user_id, season)
            except Exception:
                logger.exception("Failed to fetch Sleeper leagues for season %s", season)
                continue
            for summary in season_leagues or []:
                league_id = str(summary.get("league_id") or "")
                if not league_id or league_id in seen_league_ids:
                    continue
                chain_leagues = self._walk_chain(league_id)
                for lg in chain_leagues:
                    seen_league_ids.add(str(lg.get("league_id")))
                root_id = self._chain_root(chain_leagues)
                if not root_id:
                    continue
                display_name = summary.get("name") or chain_leagues[0].get("name") or "Unknown League"
                existing = chains_by_root.get(root_id)
                if existing:
                    merged = {str(lg.get("league_id")): lg for lg in existing.leagues}
                    for lg in chain_leagues:
                        merged[str(lg.get("league_id"))] = lg
                    existing.leagues = sorted(
                        merged.values(),
                        key=lambda item: int(item.get("season") or 0),
                        reverse=True,
                    )
                else:
                    chains_by_root[root_id] = FranchiseChain(
                        root_league_id=root_id,
                        display_name=display_name,
                        leagues=sorted(
                            chain_leagues,
                            key=lambda item: int(item.get("season") or 0),
                            reverse=True,
                        ),
                    )

        return list(chains_by_root.values())

    def sync_franchises(self, user_id: str, sleeper_user_id: str) -> List[dict]:
        """Discover chains, upsert franchise rows, and import all seasons."""
        chains = self.discover_chains(sleeper_user_id)
        results: List[dict] = []
        for chain in chains:
            franchise_id = f"franchise:{user_id}:{chain.root_league_id}"
            franchise = self.db.upsert_franchise(
                franchise_id,
                user_id,
                display_name=chain.display_name,
                canonical_sleeper_id=chain.root_league_id,
            )
            for league_payload in chain.leagues:
                sleeper_league_id = str(league_payload.get("league_id"))
                season = int(league_payload.get("season") or datetime.now().year)
                self.import_service.import_league(
                    user_id,
                    sleeper_league_id,
                    season,
                    franchise_id=franchise_id,
                )
            self.db.reassign_franchise_leagues(user_id, franchise_id)
            franchise["seasons"] = self.db.get_franchise_leagues(franchise_id, user_id)
            results.append(franchise)
        return results

    def refresh_franchise(self, user_id: str, franchise_id: str, *, current_only: bool = False) -> dict:
        """Re-import all seasons for a franchise (or current season only)."""
        franchise = self.db.get_franchise(franchise_id, user_id)
        if not franchise:
            raise LookupError("Franchise not found")
        leagues = self.db.get_franchise_leagues(franchise_id, user_id)
        if not leagues:
            raise LookupError("No imported seasons for franchise")
        targets = leagues[:1] if current_only else leagues
        refreshed: List[dict] = []
        for league_row in targets:
            sleeper_league_id = (
                league_row.get("sleeper_league_id") or league_row["league_id"].split(":", 1)[-1]
            )
            season = int(league_row.get("season") or datetime.now().year)
            league_id = self.import_service.import_league(
                user_id,
                str(sleeper_league_id),
                season,
                franchise_id=franchise_id,
            )
            refreshed.append({"league_id": league_id, "season": season})
        self.db.reassign_franchise_leagues(user_id, franchise_id)
        franchise = self.db.get_franchise(franchise_id, user_id)
        assert franchise is not None
        franchise["refreshed"] = refreshed
        franchise["seasons"] = self.db.get_franchise_leagues(franchise_id, user_id)
        return franchise

    @staticmethod
    def _walk_chain(start_league_id: str, *, max_depth: int = 25) -> List[dict]:
        """Walk backward on previous_league_id until null."""
        chain: List[dict] = []
        current_id: Optional[str] = start_league_id
        visited: Set[str] = set()
        depth = 0
        while current_id and current_id not in visited and depth < max_depth:
            visited.add(current_id)
            try:
                payload = SleeperIntegration.get_league(current_id)
            except Exception:
                logger.exception("Failed to fetch Sleeper league %s", current_id)
                break
            chain.append(payload)
            previous = payload.get("previous_league_id")
            current_id = str(previous) if previous else None
            depth += 1
        return chain

    @staticmethod
    def _chain_root(chain: List[dict]) -> str:
        if not chain:
            return ""
        oldest = chain[-1]
        return str(oldest.get("league_id") or "")


__all__ = ["FranchiseChain", "FranchiseService"]
