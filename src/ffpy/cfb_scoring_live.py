"""CFB live scoring refresh during game days."""

from __future__ import annotations

from typing import Any, Optional

from ffpy.database import FFPyDatabase


class CfbLiveScoringService:
    """Incremental stats refresh and live matchup scoring."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def refresh_week_stats(
        self,
        season: int,
        week: int,
        conferences: Optional[list[str]] = None,
    ) -> dict[str, int]:
        """Pull latest CFBD stats for a week and recompute fantasy points."""
        from ffpy.cfb_stats import compute_cfb_fantasy_points
        from ffpy.integrations.cfbd import DEFAULT_CONFERENCES

        confs = conferences or list(DEFAULT_CONFERENCES)
        stats_loaded = 0
        try:
            from ffpy.cfbverse import CFBVerseLoader

            loader = CFBVerseLoader(self.db)
            result = loader.load_cfbd_stats(
                season=season,
                start_week=week,
                end_week=week,
                conferences=confs,
                verbose=False,
            )
            stats_loaded = sum(result.values()) if isinstance(result, dict) else 0
        except Exception:
            pass

        fp_stored = compute_cfb_fantasy_points(self.db, season, conferences=confs)
        return {"stats_loaded": stats_loaded, "fantasy_points_stored": fp_stored}

    def score_league_week_live(self, league_id: str, week: int) -> list[dict]:
        """Update matchup scores for a league week."""
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        season = int(league["season"])
        return self.db.score_cfb_matchups(league_id, season, week)

    def get_live_scores(self, league_id: str, week: int) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        season = int(league["season"])
        scores = self.db.score_cfb_league_week(league_id, season, week)
        from datetime import datetime, timezone

        return {
            "league_id": league_id,
            "season": season,
            "week": week,
            "teams": scores,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
