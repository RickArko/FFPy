"""FastAPI routes for hosted college fantasy leagues (SEC / Big Ten / ACC MVP)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ffpy.auth import AuthenticatedUser
from ffpy.database import FFPyDatabase
from ffpy.integrations.cfbd import DEFAULT_CONFERENCES
from ffpy.optimizer import LineupOptimizer, Player, RosterConstraints
from ffpy.scoring import ScoringConfig


class CfbLeagueCreateRequest(BaseModel):
    name: str
    season: int = Field(..., ge=2000, le=2100)
    allowed_conferences: List[str] = Field(default_factory=lambda: list(DEFAULT_CONFERENCES))
    num_teams: int = Field(10, ge=4, le=20)
    fcs_discount_pct: float = Field(0.75, ge=0.0, le=1.0)
    scoring_preset: str = "college_standard"
    roster_preset: str = "college_standard"


class CfbTeamCreateRequest(BaseModel):
    team_name: str
    owner_name: str = ""


class CfbLineupEntry(BaseModel):
    player_id: int
    slot: str = "FLEX"
    is_starter: bool = True


class CfbLineupRequest(BaseModel):
    season: int
    week: int = Field(..., ge=1, le=16)
    entries: List[CfbLineupEntry]


class CfbOptimizeRequest(BaseModel):
    season: int
    week: int = Field(..., ge=1, le=16)


def _load_college_roster_constraints(preset: str = "college_standard") -> RosterConstraints:
    path = Path(__file__).parent.parent.parent / "config" / "roster" / f"{preset}.json"
    if path.exists():
        return RosterConstraints.from_json_file(path)
    return RosterConstraints.standard()


def _load_college_scoring_json(preset: str = "college_standard") -> str:
    path = Path(__file__).parent.parent.parent / "config" / "scoring" / f"{preset}.json"
    if path.exists():
        return path.read_text()
    return json.dumps(ScoringConfig.standard().to_dict())


def register_cfb_league_router(
    router: APIRouter,
    get_db,
    get_current_user,
    require_user: bool = True,
) -> None:
    """Attach CFB league routes to an APIRouter."""

    def _user_or_default(user: Optional[AuthenticatedUser]) -> str:
        if user:
            return user.user_id
        if not require_user:
            return "local-user"
        raise HTTPException(status_code=401, detail="Authentication required")

    @router.post("/leagues")
    def create_cfb_league(
        payload: CfbLeagueCreateRequest,
        user: Optional[AuthenticatedUser] = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        uid = _user_or_default(user)
        league_id = f"cfb:{uuid.uuid4().hex[:12]}"
        db.create_cfb_league(
            {
                "league_id": league_id,
                "user_id": uid,
                "name": payload.name,
                "season": payload.season,
                "allowed_conferences": json.dumps(payload.allowed_conferences),
                "scoring_json": _load_college_scoring_json(payload.scoring_preset),
                "roster_slots_json": json.dumps(
                    _load_college_roster_constraints(payload.roster_preset).to_dict()
                ),
                "num_teams": payload.num_teams,
                "playoff_weeks": json.dumps([15, 16]),
                "fcs_discount_pct": payload.fcs_discount_pct,
            }
        )
        return {"league_id": league_id, "name": payload.name, "season": payload.season}

    @router.get("/leagues")
    def list_cfb_leagues(
        user: Optional[AuthenticatedUser] = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[Dict[str, Any]]:
        uid = _user_or_default(user)
        return db.list_cfb_leagues(uid)

    @router.get("/leagues/{league_id}/player-pool")
    def cfb_player_pool(
        league_id: str,
        week: int = 1,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        confs = json.loads(league.get("allowed_conferences") or "[]")
        season = int(league["season"])
        players = db.get_cfb_players(season=season, conferences=confs, fantasy_eligible=True)
        projections = db.get_cfb_projections(season=season, week=week, conferences=confs)
        if not projections.empty and not players.empty:
            merged = players.merge(
                projections[["player_id", "projected_points"]],
                on="player_id",
                how="left",
            )
        else:
            merged = players
            if not merged.empty:
                merged["projected_points"] = 0.0
        return {
            "season": season,
            "week": week,
            "conferences": confs,
            "players": merged.to_dict(orient="records"),
        }

    @router.post("/leagues/{league_id}/teams")
    def create_cfb_team(
        league_id: str,
        payload: CfbTeamCreateRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        team_id = f"{league_id}:team:{uuid.uuid4().hex[:8]}"
        db.create_cfb_league_team(
            {
                "league_team_id": team_id,
                "league_id": league_id,
                "team_name": payload.team_name,
                "owner_name": payload.owner_name,
            }
        )
        return {"league_team_id": team_id, "team_name": payload.team_name}

    @router.post("/leagues/{league_id}/teams/{team_id}/lineup")
    def set_cfb_lineup(
        league_id: str,
        team_id: str,
        payload: CfbLineupRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        db.set_cfb_lineup(
            team_id,
            payload.season,
            payload.week,
            [e.model_dump() for e in payload.entries],
        )
        return {"status": "ok", "week": str(payload.week)}

    @router.get("/leagues/{league_id}/weeks/{week}/scores")
    def cfb_week_scores(
        league_id: str,
        week: int,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        season = int(league["season"])
        scores = db.score_cfb_league_week(league_id, season, week)
        return {"league_id": league_id, "season": season, "week": week, "teams": scores}

    @router.post("/leagues/{league_id}/teams/{team_id}/optimize")
    def optimize_cfb_lineup(
        league_id: str,
        team_id: str,
        payload: CfbOptimizeRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        confs = json.loads(league.get("allowed_conferences") or "[]")
        projections = db.get_cfb_projections(season=payload.season, week=payload.week, conferences=confs)
        if projections.empty:
            raise HTTPException(status_code=400, detail="No projections available for this week")

        roster_slots = json.loads(league.get("roster_slots_json") or "{}")
        constraints = (
            RosterConstraints.from_dict(roster_slots) if roster_slots else _load_college_roster_constraints()
        )

        players = [
            Player(
                name=row["full_name"],
                position=row.get("position") or "",
                team=row.get("team_key") or "",
                projected_points=float(row.get("projected_points") or 0),
            )
            for _, row in projections.iterrows()
        ]
        optimizer = LineupOptimizer(constraints=constraints)
        result = optimizer.optimize(players)
        return {
            "total_points": result.total_points,
            "starters": [
                {
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "projected_points": p.projected_points,
                }
                for p in result.starters
            ],
            "bench": [
                {
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "projected_points": p.projected_points,
                }
                for p in result.bench
            ],
        }

    @router.get("/seasons/{season}/coverage")
    def cfb_season_coverage(season: int, db: FFPyDatabase = Depends(get_db)) -> Dict[str, Any]:
        audit = db.audit_cfb_data(season=season)
        teams = db.get_cfb_teams(season=season)
        conf_counts = {}
        if not teams.empty and "conference" in teams.columns:
            conf_counts = teams.groupby("conference").size().to_dict()
        return {"season": season, "audit": audit, "teams_by_conference": conf_counts}
