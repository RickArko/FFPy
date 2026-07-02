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
    model: str = "historical"


class CfbRosterUpdateRequest(BaseModel):
    add: List[int] = Field(default_factory=list)
    drop: List[int] = Field(default_factory=list)
    slot: str = "BENCH"


class CfbTransactionCreateRequest(BaseModel):
    league_team_id: str
    tx_type: str = Field(..., pattern="^(add|drop|trade)$")
    player_id: int
    faab_bid: Optional[float] = None


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
        model: str = "historical",
        available_only: bool = False,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        confs = json.loads(league.get("allowed_conferences") or "[]")
        season = int(league["season"])
        players = db.get_cfb_players(season=season, conferences=confs, fantasy_eligible=True)
        if available_only and not players.empty:
            rostered = db.get_cfb_league_rostered_player_ids(league_id)
            players = players[~players["player_id"].isin(rostered)]
        projections = db.get_cfb_projections(season=season, week=week, model=model, conferences=confs)
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
            "model": model,
            "conferences": confs,
            "players": merged.to_dict(orient="records"),
        }

    @router.get("/leagues/{league_id}/teams")
    def list_cfb_teams(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> List[Dict[str, Any]]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        teams = db.get_cfb_league_teams(league_id)
        out = []
        for team in teams:
            roster = db.get_cfb_league_roster(team["league_team_id"])
            out.append({**team, "roster": roster.to_dict(orient="records")})
        return out

    @router.get("/leagues/{league_id}/teams/{team_id}/roster")
    def get_cfb_team_roster(
        league_id: str,
        team_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        roster = db.get_cfb_league_roster(team_id)
        return {"league_team_id": team_id, "roster": roster.to_dict(orient="records")}

    @router.post("/leagues/{league_id}/teams/{team_id}/roster")
    def update_cfb_team_roster(
        league_id: str,
        team_id: str,
        payload: CfbRosterUpdateRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        for player_id in payload.drop:
            db.drop_cfb_roster_player(team_id, player_id)
        added = []
        for player_id in payload.add:
            try:
                db.add_cfb_roster_player(team_id, player_id, slot=payload.slot)
                added.append(player_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        roster = db.get_cfb_league_roster(team_id)
        return {
            "league_team_id": team_id,
            "added": added,
            "dropped": payload.drop,
            "roster": roster.to_dict(orient="records"),
        }

    @router.get("/leagues/{league_id}/standings")
    def cfb_standings(
        league_id: str,
        through_week: int = 16,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        season = int(league["season"])
        standings = db.get_cfb_standings(league_id, season, through_week=through_week)
        return {
            "league_id": league_id,
            "season": season,
            "through_week": through_week,
            "standings": standings,
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

    @router.post("/leagues/{league_id}/weeks/{week}/matchups/generate")
    def generate_cfb_matchups(
        league_id: str,
        week: int,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        season = int(league["season"])
        count = db.generate_cfb_matchups(league_id, season, week)
        matchups = db.get_cfb_matchups(league_id, season, week)
        return {"league_id": league_id, "season": season, "week": week, "count": count, "matchups": matchups}

    @router.get("/leagues/{league_id}/weeks/{week}/matchups")
    def get_cfb_matchups(
        league_id: str,
        week: int,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        season = int(league["season"])
        matchups = db.get_cfb_matchups(league_id, season, week)
        return {"league_id": league_id, "season": season, "week": week, "matchups": matchups}

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
        matchups = db.get_cfb_matchups(league_id, season, week)
        return {
            "league_id": league_id,
            "season": season,
            "week": week,
            "teams": scores,
            "matchups": matchups,
        }

    @router.post("/leagues/{league_id}/weeks/{week}/matchups/score")
    def score_cfb_matchups(
        league_id: str,
        week: int,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        season = int(league["season"])
        results = db.score_cfb_matchups(league_id, season, week)
        return {"league_id": league_id, "season": season, "week": week, "matchups": results}

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
        projections = db.get_cfb_projections(
            season=payload.season, week=payload.week, model=payload.model, conferences=confs
        )
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
            "model": payload.model,
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

    @router.post("/leagues/{league_id}/transactions")
    def create_cfb_transaction(
        league_id: str,
        payload: CfbTransactionCreateRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        tx_id = db.create_cfb_transaction(
            {
                "league_id": league_id,
                "league_team_id": payload.league_team_id,
                "tx_type": payload.tx_type,
                "player_id": payload.player_id,
                "faab_bid": payload.faab_bid,
                "status": "pending",
            }
        )
        return {"transaction_id": tx_id, "status": "pending"}

    @router.get("/leagues/{league_id}/transactions")
    def list_cfb_transactions(
        league_id: str,
        status: Optional[str] = None,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        txs = db.list_cfb_transactions(league_id, status=status)
        return {"league_id": league_id, "transactions": txs}

    @router.get("/seasons/{season}/coverage")
    def cfb_season_coverage(season: int, db: FFPyDatabase = Depends(get_db)) -> Dict[str, Any]:
        audit = db.audit_cfb_data(season=season)
        teams = db.get_cfb_teams(season=season)
        conf_counts = {}
        if not teams.empty and "conference" in teams.columns:
            conf_counts = teams.groupby("conference").size().to_dict()
        return {"season": season, "audit": audit, "teams_by_conference": conf_counts}
