"""CFB playoff bracket generation and advancement."""

from __future__ import annotations

from typing import Any

from ffpy.database import FFPyDatabase


class CfbPlayoffService:
    """Seed playoffs from standings and advance winners."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def seed_playoffs(self, league_id: str) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        settings = self.db.get_cfb_league_settings(league_id)
        season = int(league["season"])
        reg_weeks = int(settings.get("regular_season_weeks") or 14)
        playoff_teams = int(settings.get("playoff_teams") or 4)
        start_week = int(settings.get("playoff_start_week") or 15)

        standings = self.db.get_cfb_standings(league_id, season, through_week=reg_weeks)
        seeds = standings[:playoff_teams]
        if len(seeds) < 2:
            raise ValueError("Need at least 2 teams for playoffs")

        bracket_pairs = self._bracket_pairs(seeds)
        created = 0
        for home, away in bracket_pairs:
            self.db.conn.execute(
                """
                INSERT INTO cfb_matchups (
                    league_id, season, week, home_team_id, away_team_id, is_playoff
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(league_id, season, week, home_team_id, away_team_id) DO UPDATE SET
                    is_playoff = 1
                """,
                (league_id, season, start_week, home["league_team_id"], away["league_team_id"]),
            )
            created += 1
        self.db.conn.commit()
        return self.get_bracket(league_id)

    def _bracket_pairs(self, seeds: list[dict]) -> list[tuple[dict, dict]]:
        n = len(seeds)
        if n == 2:
            return [(seeds[0], seeds[1])]
        if n == 4:
            return [(seeds[0], seeds[3]), (seeds[1], seeds[2])]
        pairs = []
        for i in range(n // 2):
            pairs.append((seeds[i], seeds[n - 1 - i]))
        return pairs

    def get_bracket(self, league_id: str) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        settings = self.db.get_cfb_league_settings(league_id)
        season = int(league["season"])
        start_week = int(settings.get("playoff_start_week") or 15)

        rows = self.db.conn.execute(
            """
            SELECT m.*, ht.team_name AS home_team_name, at.team_name AS away_team_name
            FROM cfb_matchups m
            JOIN cfb_league_teams ht ON m.home_team_id = ht.league_team_id
            JOIN cfb_league_teams at ON m.away_team_id = at.league_team_id
            WHERE m.league_id = ? AND m.season = ? AND m.is_playoff = 1
            ORDER BY m.week, m.matchup_id
            """,
            (league_id, season),
        ).fetchall()
        matchups = [dict(r) for r in rows]
        return {
            "league_id": league_id,
            "season": season,
            "playoff_start_week": start_week,
            "matchups": matchups,
        }

    def advance_playoffs(self, league_id: str, week: int) -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        season = int(league["season"])
        settings = self.db.get_cfb_league_settings(league_id)
        start_week = int(settings.get("playoff_start_week") or 15)

        self.db.score_cfb_matchups(league_id, season, week)
        matchups = self.db.get_cfb_matchups(league_id, season, week)
        winners = []
        for m in matchups:
            home = float(m.get("home_score") or 0)
            away = float(m.get("away_score") or 0)
            if home > away:
                winners.append({"league_team_id": m["home_team_id"], "team_name": m["home_team_name"]})
            elif away > home:
                winners.append({"league_team_id": m["away_team_id"], "team_name": m["away_team_name"]})

        if week == start_week and len(winners) == 2:
            next_week = week + 1
            self.db.conn.execute(
                """
                INSERT INTO cfb_matchups (
                    league_id, season, week, home_team_id, away_team_id, is_playoff
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(league_id, season, week, home_team_id, away_team_id) DO NOTHING
                """,
                (league_id, season, next_week, winners[0]["league_team_id"], winners[1]["league_team_id"]),
            )
            self.db.conn.commit()

        return self.get_bracket(league_id)
