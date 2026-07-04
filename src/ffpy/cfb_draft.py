"""CFB snake draft service — multi-user draft replacing notebook-only flow."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ffpy.database import FFPyDatabase


class CfbDraftError(ValueError):
    """Draft validation or state error."""


class CfbDraftService:
    """Manage snake drafts for hosted CFB leagues."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def _roster_slots_per_team(self, league: dict) -> int:
        return self.db._cfb_max_roster_size(league)

    def _snake_order(self, team_ids: list[str], num_picks: int) -> list[str]:
        order: list[str] = []
        n = len(team_ids)
        for pick in range(num_picks):
            rnd = pick // n
            idx = pick % n
            if rnd % 2 == 0:
                order.append(team_ids[idx])
            else:
                order.append(team_ids[n - 1 - idx])
        return order

    def start_draft(self, league_id: str, draft_type: str = "snake") -> dict[str, Any]:
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise CfbDraftError("League not found")
        existing = self.db.get_cfb_draft(league_id)
        if existing and existing.get("status") not in ("cancelled",):
            raise CfbDraftError("Draft already exists for this league")

        teams = self.db.get_cfb_league_teams(league_id)
        if len(teams) < 2:
            raise CfbDraftError("Need at least 2 teams to draft")
        team_ids = [t["league_team_id"] for t in teams]
        slots = self._roster_slots_per_team(league)
        total_picks = slots * len(team_ids)
        pick_order = self._snake_order(team_ids, total_picks)

        draft_id = f"draft:{uuid.uuid4().hex[:12]}"
        settings = {"pick_timer_sec": 90, "model": "historical"}
        self.db.create_cfb_draft(
            {
                "draft_id": draft_id,
                "league_id": league_id,
                "status": "active",
                "draft_type": draft_type,
                "current_pick": 1,
                "order_json": json.dumps(pick_order),
                "settings_json": json.dumps(settings),
            }
        )
        return self.get_board(league_id)

    def _draft_context(self, league_id: str) -> tuple[dict, dict, list[str], list[dict]]:
        draft = self.db.get_cfb_draft(league_id)
        if not draft:
            raise CfbDraftError("No draft found")
        league = self.db.get_cfb_league(league_id)
        if not league:
            raise CfbDraftError("League not found")
        order: list[str] = json.loads(draft.get("order_json") or "[]")
        picks = self.db.get_cfb_draft_picks(draft["draft_id"])
        return draft, league, order, picks

    def on_the_clock(self, league_id: str) -> Optional[str]:
        draft, _, order, picks = self._draft_context(league_id)
        if draft.get("status") != "active":
            return None
        pick_num = int(draft.get("current_pick") or 1)
        if pick_num > len(order):
            return None
        return order[pick_num - 1]

    def make_pick(self, league_id: str, team_id: str, player_id: int, is_autopick: bool = False) -> dict:
        draft, league, order, picks = self._draft_context(league_id)
        if draft.get("status") != "active":
            raise CfbDraftError("Draft is not active")

        pick_num = int(draft.get("current_pick") or 1)
        if pick_num > len(order):
            raise CfbDraftError("Draft is complete")
        expected_team = order[pick_num - 1]
        if team_id != expected_team:
            raise CfbDraftError("Not your pick")

        picked_ids = {p["player_id"] for p in picks if p.get("player_id")}
        if player_id in picked_ids:
            raise CfbDraftError("Player already drafted")

        rostered = self.db.get_cfb_league_rostered_player_ids(league_id)
        if player_id in rostered:
            raise CfbDraftError("Player already rostered")

        try:
            self.db.validate_cfb_roster_move(league_id, player_id, action="add")
        except ValueError as exc:
            raise CfbDraftError(str(exc)) from exc

        n_teams = len(self.db.get_cfb_league_teams(league_id))
        rnd = (pick_num - 1) // n_teams + 1

        self.db.add_cfb_draft_pick(
            {
                "draft_id": draft["draft_id"],
                "pick_number": pick_num,
                "round": rnd,
                "team_id": team_id,
                "player_id": player_id,
                "is_autopick": 1 if is_autopick else 0,
            }
        )
        self.db.add_cfb_roster_player(team_id, player_id, slot="BENCH")

        next_pick = pick_num + 1
        if next_pick > len(order):
            self.db.update_cfb_draft(
                draft["draft_id"],
                {"status": "complete", "current_pick": len(order)},
            )
        else:
            self.db.update_cfb_draft(draft["draft_id"], {"current_pick": next_pick})

        return self.get_board(league_id)

    def autopick(self, league_id: str, team_id: Optional[str] = None) -> dict:
        draft, league, order, picks = self._draft_context(league_id)
        clock = self.on_the_clock(league_id)
        if not clock:
            raise CfbDraftError("No team on the clock")
        team_id = team_id or clock
        if team_id != clock:
            raise CfbDraftError("Not your pick")

        season = int(league["season"])
        model = json.loads(draft.get("settings_json") or "{}").get("model", "historical")
        week = 1

        confs = json.loads(league.get("allowed_conferences") or "[]")
        projections = self.db.get_cfb_projections(season=season, week=week, model=model, conferences=confs)
        if projections.empty:
            raise CfbDraftError("No projections available for autopick")

        picked_ids = {p["player_id"] for p in picks if p.get("player_id")}
        rostered = self.db.get_cfb_league_rostered_player_ids(league_id)
        taken = picked_ids | rostered

        roster = self.db.get_cfb_league_roster(team_id)
        pos_counts: dict[str, int] = {}
        for _, row in roster.iterrows():
            pos = row.get("position") or "FLEX"
            pos_counts[pos] = pos_counts.get(pos, 0) + 1

        candidates = projections[~projections["player_id"].isin(taken)].copy()
        if candidates.empty:
            raise CfbDraftError("No available players for autopick")

        candidates = candidates.sort_values("projected_points", ascending=False)
        best_id = int(candidates.iloc[0]["player_id"])
        return self.make_pick(league_id, team_id, best_id, is_autopick=True)

    def get_board(self, league_id: str) -> dict[str, Any]:
        draft = self.db.get_cfb_draft(league_id)
        if not draft:
            return {"status": "none"}
        league = self.db.get_cfb_league(league_id)
        order: list[str] = json.loads(draft.get("order_json") or "[]")
        picks = self.db.get_cfb_draft_picks(draft["draft_id"])
        pick_num = int(draft.get("current_pick") or 1)
        if draft.get("status") == "complete":
            pick_num = len(order)
        on_clock = order[pick_num - 1] if draft.get("status") == "active" and pick_num <= len(order) else None

        picked_ids = {p["player_id"] for p in picks if p.get("player_id")}
        season = int(league["season"]) if league else 2024
        confs = json.loads(league.get("allowed_conferences") or "[]") if league else []
        players = self.db.get_cfb_players(season=season, conferences=confs, fantasy_eligible=True)
        if not players.empty:
            available = players[~players["player_id"].isin(picked_ids)]
        else:
            available = players

        teams = {t["league_team_id"]: t for t in self.db.get_cfb_league_teams(league_id)}

        return {
            "draft_id": draft["draft_id"],
            "league_id": league_id,
            "status": draft["status"],
            "draft_type": draft["draft_type"],
            "current_pick": pick_num,
            "total_picks": len(order),
            "on_the_clock": on_clock,
            "on_the_clock_team": teams.get(on_clock, {}).get("team_name") if on_clock else None,
            "picks": picks,
            "available_count": len(available) if not available.empty else 0,
            "settings": json.loads(draft.get("settings_json") or "{}"),
        }
