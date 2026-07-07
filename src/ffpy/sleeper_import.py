"""Shared Sleeper league import and draft-help helpers."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ffpy.database import FFPyDatabase
from ffpy.draft_strategy import (
    DEFAULT_STARTER_SLOTS,
    DraftStrategyConfig,
    DraftStrategyEngine,
    load_sleeper_players,
)
from ffpy.integrations.sleeper import SleeperIntegration

logger = logging.getLogger(__name__)


class DraftHelpRequest(BaseModel):
    team_id: str
    num_players: int = Field(100, ge=1, le=200)
    pick_slots: Optional[List[int]] = None
    num_teams: int = Field(10, ge=4, le=20)
    draft_order: Optional[List[str]] = None


def compute_snake_pick_slots(position: int, num_teams: int, num_rounds: int = 3) -> List[int]:
    """Return snake-draft pick numbers for the team at ``position`` (1-indexed)."""
    slots: List[int] = []
    for r in range(1, num_rounds + 1):
        if r % 2 == 1:
            slots.append((r - 1) * num_teams + position)
        else:
            slots.append(r * num_teams - position + 1)
    return slots


def scoring_type_from_sleeper(scoring_settings: Optional[dict]) -> str:
    """Map Sleeper scoring_settings to a coarse scoring_type label."""
    if not scoring_settings:
        return "custom"
    rec = float(scoring_settings.get("rec") or 0)
    if rec >= 1.0:
        return "ppr"
    if rec >= 0.5:
        return "half_ppr"
    if rec == 0:
        return "standard"
    return "custom"


def starter_slots_from_sleeper(league_payload: dict) -> Dict[str, int]:
    """Derive DraftStrategyConfig.starter_slots from Sleeper roster_positions."""
    roster_positions = league_payload.get("roster_positions") or []
    slots: Dict[str, int] = {}
    for raw_pos in roster_positions:
        pos = str(raw_pos or "").upper()
        if pos in ("BN", "IR", "TAX", "REC", "RESERVE"):
            continue
        key = "DST" if pos in ("DEF", "D/ST") else pos
        if key in ("QB", "RB", "WR", "TE", "FLEX", "K", "DST", "OP"):
            slots[key] = slots.get(key, 0) + 1
    return slots or dict(DEFAULT_STARTER_SLOTS)


def import_from_sleeper(league_id: str, season: int) -> dict:
    """Fetch a Sleeper league snapshot for storage via FFPyDatabase.store_user_league."""
    league = SleeperIntegration.get_league(league_id)
    rosters = SleeperIntegration.get_rosters(league_id)
    users = SleeperIntegration.get_league_users(league_id)
    user_by_id = {str(u.get("user_id")): u for u in users}
    players_map = load_sleeper_players()

    teams = []
    for idx, r in enumerate(rosters):
        players_list = r.get("players") or []
        owner_id = str(r.get("owner_id")) if r.get("owner_id") is not None else ""
        if not owner_id and not players_list:
            continue
        roster_id = r.get("roster_id")
        user = user_by_id.get(owner_id, {})
        metadata = user.get("metadata") or {}
        fallback_id = str(roster_id) if roster_id is not None else owner_id or str(idx + 1)
        team_name = (
            metadata.get("team_name")
            or user.get("display_name")
            or (f"Team {fallback_id}" if fallback_id else "Unknown")
        )
        owner_display = user.get("display_name") or owner_id or "Unknown"
        team_id_suffix = str(roster_id) if roster_id is not None else owner_id or str(idx + 1)
        teams.append(
            {
                "team_id": f"sleeper:{league_id}:{team_id_suffix}",
                "name": team_name,
                "owner": owner_display,
                "owner_id": owner_id,
                "wins": r.get("settings", {}).get("wins", 0),
                "losses": r.get("settings", {}).get("losses", 0),
                "ties": r.get("settings", {}).get("ties", 0),
                "points_for": r.get("settings", {}).get("fpts", 0),
                "points_against": r.get("settings", {}).get("fpts_against", 0),
                "rank": None,
                "roster": SleeperIntegration.enrich_roster(r.get("players", []), players_map),
            }
        )

    teams.sort(key=lambda t: (-(t.get("wins") or 0), -(t.get("points_for") or 0)))

    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = SleeperIntegration.get_matchups(league_id, week)
        except Exception:
            break
        if not week_matchups:
            break
        by_matchup: dict = defaultdict(list)
        for m in week_matchups:
            matchup_id = m.get("matchup_id")
            roster_id = m.get("roster_id")
            if matchup_id is None or roster_id is None:
                continue
            by_matchup[matchup_id].append(m)
        for group in by_matchup.values():
            if len(group) < 2:
                continue
            home, away = group[0], group[1]
            matchups.append(
                {
                    "week": week,
                    "home_team_id": f"sleeper:{league_id}:{home.get('roster_id')}",
                    "away_team_id": f"sleeper:{league_id}:{away.get('roster_id')}",
                    "home_score": home.get("points"),
                    "away_score": away.get("points"),
                    "is_playoff": 0,
                    "is_consolation": 0,
                }
            )

    scoring_settings = league.get("scoring_settings") or {}
    league_meta = {
        "league_id": f"sleeper:{league_id}",
        "provider": "sleeper",
        "name": league.get("name", "Unknown"),
        "season": league.get("season", season),
        "scoring_type": scoring_type_from_sleeper(scoring_settings),
        "roster_size": None,
        "num_teams": league.get("total_rosters") or len(teams),
        "playoff_teams": league.get("settings", {}).get("playoff_teams"),
        "roster_positions": league.get("roster_positions"),
        "scoring_settings": scoring_settings,
        "status": league.get("status"),
        "previous_league_id": league.get("previous_league_id"),
        "sleeper_league_id": str(league_id),
    }
    return {
        "league": league_meta,
        "teams": teams,
        "matchups": matchups,
    }


def resolve_pick_slots(
    *,
    payload: DraftHelpRequest,
    num_teams: int,
    draft_slot: Optional[int] = None,
) -> List[int]:
    """Compute snake pick slots from explicit input, draft order, or draft slot."""
    if payload.pick_slots:
        return payload.pick_slots
    if payload.draft_order:
        try:
            pos = payload.draft_order.index(payload.team_id) + 1
            return compute_snake_pick_slots(pos, num_teams)
        except ValueError as exc:
            raise ValueError("Your team is not in the draft order") from exc
    if draft_slot is not None and draft_slot >= 1:
        return compute_snake_pick_slots(draft_slot, num_teams)
    return compute_snake_pick_slots(1, num_teams)


def run_draft_help(
    db: FFPyDatabase,
    *,
    league: dict,
    teams: List[dict],
    payload: DraftHelpRequest,
    sleeper_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run DraftStrategyEngine for a league team."""
    team = next((t for t in teams if t["team_id"] == payload.team_id), None)
    if not team:
        raise LookupError("Team not found")

    league_settings = json.loads(league.get("league_json") or "{}")
    num_teams = payload.num_teams or int(league.get("num_teams") or league_settings.get("num_teams") or 10)

    draft_slot: Optional[int] = None
    if sleeper_user_id:
        for roster in SleeperIntegration.get_rosters(
            str(league_settings.get("sleeper_league_id") or league["league_id"].split(":", 1)[-1])
        ):
            if roster.get("owner_id") == sleeper_user_id:
                draft_slot = roster.get("settings", {}).get("draft_slot")
                break

    pick_slots = resolve_pick_slots(payload=payload, num_teams=num_teams, draft_slot=draft_slot)
    starter_slots = starter_slots_from_sleeper(league_settings)
    config = DraftStrategyConfig(
        num_teams=num_teams,
        pick_slots=pick_slots,
        starter_slots=starter_slots,
    )
    engine = DraftStrategyEngine(db, config)
    provider = (league.get("provider") or "").lower()
    sleeper_players = load_sleeper_players() if provider == "sleeper" else None
    return engine.generate(
        league=league,
        teams=teams,
        my_team_id=payload.team_id,
        num_players=payload.num_players,
        sleeper_players=sleeper_players,
    )


__all__ = [
    "DraftHelpRequest",
    "compute_snake_pick_slots",
    "import_from_sleeper",
    "resolve_pick_slots",
    "run_draft_help",
    "scoring_type_from_sleeper",
    "starter_slots_from_sleeper",
]
