"""Unified FastAPI app hosting both pick'em tester and league manager."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from ffpy.config import Config
from ffpy.league_api import create_league_app
from ffpy.pickem_web import create_app as create_pickem_app

logger = logging.getLogger(__name__)


def create_unified_app(
    db_path: Optional[str] = None,
    *,
    require_auth: Optional[bool] = None,
) -> FastAPI:
    """App factory combining pick'em and league managers under path prefixes."""
    root = FastAPI(
        title="FFPy",
        version="0.1.0",
        description="Unified pick'em tester and fantasy league manager.",
    )

    # Pick'em app mounted at /pickem
    pickem = create_pickem_app(db_path=db_path, require_auth=require_auth)
    root.mount("/pickem", pickem)

    # League manager mounted at /league
    league = create_league_app(db_path=db_path, require_auth=require_auth)
    root.mount("/league", league)

    @root.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/league/")

    @root.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "database_path": db_path or Config.DATABASE_PATH,
            "services": ["pickem", "league"],
        }

    return root


def main() -> None:
    """CLI entry point for the unified FFPy web app."""
    parser = argparse.ArgumentParser(description="Run the unified FFPy web app.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")), help="Port to listen on.")
    parser.add_argument("--db-path", default=None, help="Optional SQLite database path override.")
    args = parser.parse_args()

    app = create_unified_app(db_path=args.db_path)
    logger.info(
        "Starting unified FFPy app on %s:%s with database=%s",
        args.host,
        args.port,
        app.state.db_path if hasattr(app.state, "db_path") else Config.DATABASE_PATH,
    )
    uvicorn.run(app, host=args.host, port=args.port)


__all__ = ["create_unified_app", "main"]


if __name__ == "__main__":
    main()
