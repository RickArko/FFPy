"""FastAPI factory for the ffpy-sleeper standalone app."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from ffpy.auth import (
    AuthenticatedUser,
    TokenVerificationError,
    TokenVerifier,
    build_token_verifier_from_config,
)
from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.sleeper_web.routes import (
    register_franchise_routes,
    register_league_routes,
    register_profile_routes,
)

logger = logging.getLogger(__name__)


def create_sleeper_app(
    db_path: Optional[str] = None,
    *,
    require_auth: Optional[bool] = None,
    auth_verifier: Optional[TokenVerifier] = None,
) -> FastAPI:
    """App factory for the Sleeper League Manager."""
    resolved_db_path = db_path or Config.DATABASE_PATH
    static_dir = Path(__file__).parent / "web"
    auth_enabled = Config.WEB_AUTH_ENABLED if require_auth is None else require_auth
    resolved_auth_verifier = auth_verifier or build_token_verifier_from_config()
    if auth_enabled and resolved_auth_verifier is None:
        raise ValueError("Auth is enabled but no token verifier is configured")

    app = FastAPI(
        title="FFPy Sleeper League Manager",
        version="0.1.0",
        description="Standalone Sleeper franchise sync and draft help.",
    )
    app.state.db_path = resolved_db_path
    app.state.auth_enabled = auth_enabled

    bearer = HTTPBearer(auto_error=False)

    def get_db():
        db = FFPyDatabase(db_path=resolved_db_path)
        try:
            yield db
        finally:
            db.close()

    def get_current_user(
        token: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> AuthenticatedUser:
        if not auth_enabled:
            return AuthenticatedUser(
                user_id="dev-user",
                email="dev@local",
                role="authenticated",
                email_confirmed=True,
                claims={},
            )
        if not token:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        assert resolved_auth_verifier is not None
        try:
            return resolved_auth_verifier.verify_access_token(token.credentials)
        except TokenVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def get_league_or_404(db: FFPyDatabase, league_id: str, user: AuthenticatedUser) -> dict:
        if not auth_enabled:
            league = db.get_league_by_id(league_id)
        else:
            league = db.get_user_league(league_id, user.user_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        return league

    def get_teams(db: FFPyDatabase, league_id: str, user: AuthenticatedUser) -> List[dict]:
        if not auth_enabled:
            return db.get_teams_for_league(league_id)
        return db.get_league_teams(league_id, user.user_id)

    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir)), name="sleeper_assets")

    @app.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "app": "ffpy-sleeper",
            "database_path": resolved_db_path,
            "auth_required": auth_enabled,
        }

    @app.get("/api/auth/me")
    def auth_me(user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
        is_real = auth_enabled and user.user_id not in ("anon", "dev-user")
        return {
            "authenticated": is_real or not auth_enabled,
            "auth_required": auth_enabled,
            "user": user.to_dict() if (is_real or not auth_enabled) else None,
        }

    @app.get("/api/auth/config")
    def auth_config(request: Request) -> Dict[str, Any]:
        browser_auth_available = bool(auth_enabled and Config.SUPABASE_URL and Config.SUPABASE_BROWSER_KEY)
        public_app_url = Config.PUBLIC_APP_URL.rstrip("/")
        request_origin = str(request.base_url).rstrip("/")
        if public_app_url.startswith("http://localhost") and not request_origin.startswith(
            ("http://localhost", "http://127.0.0.1", "http://testserver")
        ):
            public_app_url = request_origin
        auth_redirect_url = f"{public_app_url}/"
        return {
            "auth_required": auth_enabled,
            "browser_auth_available": browser_auth_available,
            "supabase_url": Config.SUPABASE_URL if browser_auth_available else None,
            "supabase_anon_key": Config.SUPABASE_BROWSER_KEY if browser_auth_available else None,
            "public_app_url": public_app_url,
            "auth_redirect_url": auth_redirect_url,
        }

    from fastapi import APIRouter

    profile_router = APIRouter(prefix="/api/profile", tags=["profile"])
    register_profile_routes(profile_router, get_db=get_db, get_current_user=get_current_user)

    franchise_router = APIRouter(prefix="/api/franchises", tags=["franchises"])
    register_franchise_routes(franchise_router, get_db=get_db, get_current_user=get_current_user)

    league_router = APIRouter(prefix="/api/leagues", tags=["leagues"])
    register_league_routes(
        league_router,
        get_db=get_db,
        get_current_user=get_current_user,
        get_league_or_404=get_league_or_404,
        get_teams=get_teams,
    )

    app.include_router(profile_router)
    app.include_router(franchise_router)
    app.include_router(league_router)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


def main() -> None:
    """CLI entry point: ffpy-sleeper."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the FFPy Sleeper League Manager.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8002")))
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    app = create_sleeper_app(db_path=args.db_path)
    logger.info(
        "Starting ffpy-sleeper on %s:%s db=%s auth=%s",
        args.host,
        args.port,
        app.state.db_path,
        app.state.auth_enabled,
    )
    uvicorn.run(app, host=args.host, port=args.port)


__all__ = ["create_sleeper_app", "main"]
