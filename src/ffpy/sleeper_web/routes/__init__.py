"""Route handlers for the ffpy-sleeper standalone app."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ffpy.auth import AuthenticatedUser
from ffpy.database import FFPyDatabase
from ffpy.sleeper_import import DraftHelpRequest, run_draft_help
from ffpy.sleeper_web.franchise import FranchiseService
from ffpy.sleeper_web.profile import ProfileLinkError, SleeperProfileService


class SleeperProfileUpdate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)


def register_profile_routes(
    router: APIRouter,
    *,
    get_db,
    get_current_user,
) -> None:
    @router.get("/sleeper")
    def get_sleeper_profile(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        profile = SleeperProfileService(db).get_profile(user.user_id)
        return {"profile": profile}

    @router.put("/sleeper")
    def link_sleeper_profile(
        payload: SleeperProfileUpdate,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        service = SleeperProfileService(db)
        try:
            profile = service.link_username(user.user_id, payload.username)
        except ProfileLinkError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"profile": profile}


def register_franchise_routes(
    router: APIRouter,
    *,
    get_db,
    get_current_user,
) -> None:
    @router.post("/sync")
    def sync_franchises(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        profile = SleeperProfileService(db).get_profile(user.user_id)
        if not profile:
            raise HTTPException(status_code=400, detail="Link a Sleeper profile before syncing")
        franchises = FranchiseService(db).sync_franchises(
            user.user_id,
            profile["sleeper_user_id"],
        )
        return {"franchises": franchises}

    @router.get("")
    def list_franchises(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        return db.list_franchises(user.user_id)

    @router.post("/{franchise_id}/refresh")
    def refresh_franchise(
        franchise_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
        current_only: bool = False,
    ) -> dict:
        service = FranchiseService(db)
        try:
            return service.refresh_franchise(user.user_id, franchise_id, current_only=current_only)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def register_league_routes(
    router: APIRouter,
    *,
    get_db,
    get_current_user,
    get_league_or_404,
    get_teams,
) -> None:
    @router.get("/{league_id}")
    def get_league(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> dict:
        return get_league_or_404(db, league_id, user)

    @router.get("/{league_id}/teams")
    def get_teams_route(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        get_league_or_404(db, league_id, user)
        return get_teams(db, league_id, user)

    @router.post("/{league_id}/draft-help")
    def draft_help(
        league_id: str,
        payload: DraftHelpRequest,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = get_league_or_404(db, league_id, user)
        teams = get_teams(db, league_id, user)
        profile = SleeperProfileService(db).get_profile(user.user_id)
        sleeper_user_id = profile["sleeper_user_id"] if profile else None
        try:
            return run_draft_help(
                db,
                league=league,
                teams=teams,
                payload=payload,
                sleeper_user_id=sleeper_user_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/{league_id}")
    def delete_league(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        league = get_league_or_404(db, league_id, user)
        db.delete_user_league(league_id, league["user_id"])
        return {"status": "deleted"}


__all__ = [
    "register_franchise_routes",
    "register_league_routes",
    "register_profile_routes",
]
