"""FastAPI routes for hosted college fantasy leagues (SEC / Big Ten / ACC MVP)."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
    drop_player_id: Optional[int] = None
    faab_bid: Optional[float] = None
    week: Optional[int] = Field(None, ge=1, le=16)


class CfbLeagueSettingsPatch(BaseModel):
    waiver_type: Optional[str] = Field(None, pattern="^(none|faab|rolling)$")
    faab_budget: Optional[float] = Field(None, ge=0)
    waiver_run_day: Optional[int] = Field(None, ge=0, le=6)
    waiver_run_hour_utc: Optional[int] = Field(None, ge=0, le=23)
    trade_deadline_week: Optional[int] = Field(None, ge=1, le=16)
    trade_review_hours: Optional[int] = Field(None, ge=0)
    veto_threshold: Optional[int] = Field(None, ge=0)
    playoff_teams: Optional[int] = Field(None, ge=2, le=16)
    playoff_start_week: Optional[int] = Field(None, ge=1, le=16)
    regular_season_weeks: Optional[int] = Field(None, ge=1, le=16)
    lineup_lock: Optional[str] = Field(None, pattern="^(individual_game|weekly)$")


class CfbDraftPickRequest(BaseModel):
    player_id: int


class CfbWaiverRunRequest(BaseModel):
    week: int = Field(..., ge=1, le=16)


class CfbTradeProposeRequest(BaseModel):
    proposer_team_id: str
    recipient_team_id: str
    items: List[Dict[str, Any]]
    week: int = Field(1, ge=1, le=16)


class CfbTradeAcceptRequest(BaseModel):
    accepting_team_id: str


class CfbTradeVetoRequest(BaseModel):
    team_id: str


class CfbDraftHelpRequest(BaseModel):
    team_id: str
    num_players: int = Field(50, ge=1, le=200)
    model: str = "historical"
    week: int = Field(1, ge=1, le=16)


# In-memory draft event subscribers (Phase I)
_draft_subscribers: dict[str, list[asyncio.Queue]] = {}


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

    @router.get("/leagues/{league_id}")
    def get_cfb_league_detail(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_cfb_league(league_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        settings = db.get_cfb_league_settings(league_id)
        return {**league, "settings": settings}

    @router.patch("/leagues/{league_id}")
    def patch_cfb_league(
        league_id: str,
        payload: CfbLeagueSettingsPatch,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        updates = payload.model_dump(exclude_none=True)
        settings = db.update_cfb_league_settings(league_id, updates)
        return {"league_id": league_id, "settings": settings}

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
        for entry in payload.entries:
            if db.is_player_locked(league_id, entry.player_id, payload.season, payload.week):
                raise HTTPException(
                    status_code=400,
                    detail=f"Player {entry.player_id} is locked for week {payload.week}",
                )
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
        from ffpy.cfb_waivers import CfbWaiverError, CfbWaiverService

        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        if payload.tx_type == "add":
            try:
                tx_id = CfbWaiverService(db).submit_claim(
                    league_id,
                    payload.league_team_id,
                    payload.player_id,
                    drop_player_id=payload.drop_player_id,
                    faab_bid=payload.faab_bid,
                    week=payload.week,
                )
                return {"transaction_id": tx_id, "status": "pending"}
            except CfbWaiverError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        tx_id = db.create_cfb_transaction(
            {
                "league_id": league_id,
                "league_team_id": payload.league_team_id,
                "tx_type": payload.tx_type,
                "player_id": payload.player_id,
                "faab_bid": payload.faab_bid,
                "status": "pending",
                "week": payload.week,
            }
        )
        return {"transaction_id": tx_id, "status": "pending"}

    @router.post("/leagues/{league_id}/waiver-run")
    def run_cfb_waivers(
        league_id: str,
        payload: CfbWaiverRunRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_waivers import CfbWaiverError, CfbWaiverService

        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        try:
            return CfbWaiverService(db).run_waivers(league_id, payload.week)
        except CfbWaiverError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/leagues/{league_id}/transactions")
    def list_cfb_transactions(
        league_id: str,
        status: Optional[str] = None,
        week: Optional[int] = None,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        txs = db.list_cfb_transactions(league_id, status=status, week=week)
        return {"league_id": league_id, "transactions": txs}

    @router.post("/leagues/{league_id}/draft/start")
    def start_cfb_draft(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft import CfbDraftError, CfbDraftService

        try:
            board = CfbDraftService(db).start_draft(league_id)
            draft_id = board.get("draft_id")
            if draft_id:
                for q in _draft_subscribers.get(draft_id, []):
                    q.put_nowait({"event": "draft_started", "board": board})
            return board
        except CfbDraftError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/leagues/{league_id}/draft")
    def get_cfb_draft_board(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft import CfbDraftService

        board = CfbDraftService(db).get_board(league_id)
        if board.get("status") == "none":
            raise HTTPException(status_code=404, detail="No draft found")
        return board

    @router.post("/leagues/{league_id}/draft/pick")
    def cfb_draft_pick(
        league_id: str,
        payload: CfbDraftPickRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft import CfbDraftError, CfbDraftService

        svc = CfbDraftService(db)
        team_id = svc.on_the_clock(league_id)
        if not team_id:
            raise HTTPException(status_code=400, detail="No team on the clock")
        try:
            board = svc.make_pick(league_id, team_id, payload.player_id)
            draft_id = board.get("draft_id")
            if draft_id:
                for q in _draft_subscribers.get(draft_id, []):
                    q.put_nowait({"event": "pick_made", "board": board})
            return board
        except CfbDraftError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/leagues/{league_id}/draft/autopick")
    def cfb_draft_autopick(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft import CfbDraftError, CfbDraftService

        try:
            board = CfbDraftService(db).autopick(league_id)
            draft_id = board.get("draft_id")
            if draft_id:
                for q in _draft_subscribers.get(draft_id, []):
                    q.put_nowait({"event": "pick_made", "board": board})
            return board
        except CfbDraftError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/leagues/{league_id}/draft/events")
    async def cfb_draft_events(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ):
        draft = db.get_cfb_draft(league_id)
        if not draft:
            raise HTTPException(status_code=404, detail="No draft found")
        draft_id = draft["draft_id"]
        queue: asyncio.Queue = asyncio.Queue()
        _draft_subscribers.setdefault(draft_id, []).append(queue)

        async def event_stream():
            from ffpy.cfb_draft import CfbDraftService

            try:
                initial = CfbDraftService(db).get_board(league_id)
                yield f"data: {json.dumps({'event': 'connected', 'board': initial})}\n\n"
                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(msg)}\n\n"
                        if msg.get("board", {}).get("status") == "complete":
                            break
                    except TimeoutError:
                        yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
            finally:
                subs = _draft_subscribers.get(draft_id, [])
                if queue in subs:
                    subs.remove(queue)
                if not subs:
                    _draft_subscribers.pop(draft_id, None)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/leagues/{league_id}/trades")
    def propose_cfb_trade(
        league_id: str,
        payload: CfbTradeProposeRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_trades import CfbTradeError, CfbTradeService

        try:
            return CfbTradeService(db).propose(
                league_id,
                payload.proposer_team_id,
                payload.recipient_team_id,
                payload.items,
                week=payload.week,
            )
        except CfbTradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/leagues/{league_id}/trades/{trade_id}/accept")
    def accept_cfb_trade(
        league_id: str,
        trade_id: str,
        payload: CfbTradeAcceptRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_trades import CfbTradeError, CfbTradeService

        try:
            return CfbTradeService(db).accept(league_id, trade_id, payload.accepting_team_id)
        except CfbTradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/leagues/{league_id}/trades/{trade_id}/veto")
    def veto_cfb_trade(
        league_id: str,
        trade_id: str,
        payload: CfbTradeVetoRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_trades import CfbTradeError, CfbTradeService

        try:
            return CfbTradeService(db).veto(league_id, trade_id, payload.team_id)
        except CfbTradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/leagues/{league_id}/trades")
    def list_cfb_trades(
        league_id: str,
        status: Optional[str] = None,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_trades import CfbTradeService

        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")
        return {"league_id": league_id, "trades": CfbTradeService(db).list_trades(league_id, status)}

    @router.get("/leagues/{league_id}/weeks/{week}/live")
    async def cfb_live_scores_sse(
        league_id: str,
        week: int,
        db: FFPyDatabase = Depends(get_db),
    ):
        from ffpy.cfb_scoring_live import CfbLiveScoringService

        if not db.get_cfb_league(league_id):
            raise HTTPException(status_code=404, detail="League not found")

        async def score_stream():
            svc = CfbLiveScoringService(db)
            for _ in range(3):
                payload = svc.get_live_scores(league_id, week)
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'event': 'done'})}\n\n"

        return StreamingResponse(score_stream(), media_type="text/event-stream")

    @router.post("/leagues/{league_id}/playoffs/seed")
    def seed_cfb_playoffs(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_playoffs import CfbPlayoffService

        try:
            return CfbPlayoffService(db).seed_playoffs(league_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/leagues/{league_id}/playoffs/bracket")
    def get_cfb_playoff_bracket(
        league_id: str,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_playoffs import CfbPlayoffService

        try:
            return CfbPlayoffService(db).get_bracket(league_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/leagues/{league_id}/draft-help")
    def cfb_draft_help(
        league_id: str,
        payload: CfbDraftHelpRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft_strategy import CfbDraftStrategyConfig, CfbDraftStrategyEngine

        config = CfbDraftStrategyConfig(model=payload.model, week=payload.week)
        engine = CfbDraftStrategyEngine(db, config)
        try:
            return engine.generate(league_id, payload.team_id, num_players=payload.num_players)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/players/{player_id}/outlook")
    def cfb_player_outlook(
        player_id: int,
        season: int,
        week: int = 1,
        model: str = "historical",
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        from ffpy.cfb_draft_strategy import CfbDraftStrategyConfig, CfbDraftStrategyEngine

        config = CfbDraftStrategyConfig(model=model, week=week)
        engine = CfbDraftStrategyEngine(db, config)
        try:
            return engine.player_outlook(player_id, season, week)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/seasons/{season}/coverage")
    def cfb_season_coverage(season: int, db: FFPyDatabase = Depends(get_db)) -> Dict[str, Any]:
        audit = db.audit_cfb_data(season=season)
        teams = db.get_cfb_teams(season=season)
        conf_counts = {}
        if not teams.empty and "conference" in teams.columns:
            conf_counts = teams.groupby("conference").size().to_dict()
        return {"season": season, "audit": audit, "teams_by_conference": conf_counts}
