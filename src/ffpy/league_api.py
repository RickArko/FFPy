"""FastAPI backend for the FFPy League Manager."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ffpy.auth import (
    AuthenticatedUser,
    TokenVerificationError,
    TokenVerifier,
    build_token_verifier_from_config,
)
from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.integrations.sleeper import SleeperIntegration
from ffpy.integrations.yahoo import YahooIntegration
from ffpy.league_crypto import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)

MASTER_KEY = Config.SUPABASE_JWT_SECRET.encode() if Config.SUPABASE_JWT_SECRET else b""

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CredentialStoreRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(espn|yahoo|sleeper)$")
    credentials: Dict[str, Any]
    label: str = ""


class LeagueImportRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(espn|yahoo|sleeper)$")
    league_id: str
    season: int = Field(..., ge=2000, le=2100)
    sleeper_username: Optional[str] = None  # local/no-auth: key imports to this user


class OptimizeRequest(BaseModel):
    team_id: str
    week: int = Field(..., ge=1, le=25)


class DraftHelpRequest(BaseModel):
    team_id: str
    num_players: int = Field(100, ge=1, le=200)
    pick_slots: Optional[List[int]] = None
    num_teams: int = Field(10, ge=4, le=20)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_auth_verifier() -> Optional[TokenVerifier]:
    return build_token_verifier_from_config()


def _get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[AuthenticatedUser]:
    verifier = _get_auth_verifier()
    if verifier is None:
        return None
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    try:
        return verifier.verify_access_token(credentials.credentials)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> AuthenticatedUser:
    user = _get_current_user(credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _import_from_espn(league_id: str, season: int, creds: dict) -> dict:
    integration = ESPNLeagueIntegration(
        league_id=int(league_id),
        season=season,
        swid=creds.get("swid"),
        espn_s2=creds.get("s2"),
    )
    info = integration.get_league_info()
    teams = integration.get_all_teams()

    # Fetch all rosters in a single ESPN API call (mRoster view returns entire league)
    all_rosters = integration.get_all_rosters()

    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = integration.get_matchups(week)
            for m in week_matchups:
                matchups.append(
                    {
                        "week": week,
                        "home_team_id": f"espn:{league_id}:{m['home_team_id']}",
                        "away_team_id": f"espn:{league_id}:{m['away_team_id']}",
                        "home_score": m.get("home_score"),
                        "away_score": m.get("away_score"),
                        "is_playoff": 0,
                        "is_consolation": 0,
                    }
                )
        except Exception:
            # ESPN returns empty schedule for future weeks; stop when we hit the first failure
            break

    team_list = []
    for t in teams:
        team_id = t["id"]
        roster = all_rosters.get(team_id, pd.DataFrame())
        team_list.append(
            {
                "team_id": f"espn:{league_id}:{team_id}",
                "name": t["name"],
                "owner": t.get("owner", "Unknown"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": t.get("points_for", 0),
                "points_against": t.get("points_against", 0),
                "rank": t.get("rank"),
                "roster": roster.to_dict(orient="records") if not roster.empty else [],
            }
        )
    return {
        "league": {
            "league_id": f"espn:{league_id}",
            "provider": "espn",
            "name": info.get("name", "Unknown"),
            "season": season,
            "scoring_type": info.get("scoring_type", "custom").lower().replace("-", "_"),
            "roster_size": info.get("size"),
            "num_teams": info.get("size"),
            "playoff_teams": info.get("playoff_teams"),
        },
        "teams": team_list,
        "matchups": matchups,
    }


def _import_from_yahoo(league_id: str, season: int, creds: dict) -> dict:
    client_id = creds.get("client_id") or os.getenv("YAHOO_CLIENT_ID", "")
    client_secret = creds.get("client_secret") or os.getenv("YAHOO_CLIENT_SECRET", "")
    access_token = creds.get("access_token", "")
    integration = YahooIntegration(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=creds.get("redirect_uri", "http://localhost:8001"),
    )
    meta = integration.get_league_metadata(league_id, access_token)
    standings = integration.get_standings(league_id, access_token)
    teams = []
    for s in standings:
        team_key = s.get("team_key", "")
        roster = integration.get_team_roster(team_key, access_token) if team_key else []
        teams.append(
            {
                "team_id": f"yahoo:{league_id}:{team_key}",
                "name": s.get("name", "Unknown"),
                "owner": s.get("manager", {}).get("nickname", "Unknown"),
                "wins": s.get("standings", {}).get("outcome_totals", {}).get("wins", 0),
                "losses": s.get("standings", {}).get("outcome_totals", {}).get("losses", 0),
                "ties": s.get("standings", {}).get("outcome_totals", {}).get("ties", 0),
                "points_for": s.get("standings", {}).get("points_for", 0),
                "points_against": s.get("standings", {}).get("points_against", 0),
                "rank": s.get("standings", {}).get("rank"),
                "roster": roster if isinstance(roster, list) else [],
            }
        )
    matchups: List[dict] = []
    for week in range(1, 18):
        try:
            week_matchups = integration.get_matchups(league_id, week, access_token)
            for m in week_matchups:
                teams_in = m.get("teams", {})
                home = away = None
                for key, val in teams_in.items():
                    if not isinstance(val, dict):
                        continue
                    t = val.get("team", [])
                    if isinstance(t, list) and len(t) > 1:
                        tk = t[0].get("team_key", "")
                        if home is None:
                            home = tk
                        else:
                            away = tk
                if home and away:
                    matchups.append(
                        {
                            "week": week,
                            "home_team_id": f"yahoo:{league_id}:{home}",
                            "away_team_id": f"yahoo:{league_id}:{away}",
                            "home_score": None,
                            "away_score": None,
                            "is_playoff": 0,
                            "is_consolation": 0,
                        }
                    )
        except Exception:
            break
    return {
        "league": {
            "league_id": f"yahoo:{league_id}",
            "provider": "yahoo",
            "name": meta.get("name", "Unknown"),
            "season": season,
            "scoring_type": "custom",
            "roster_size": None,
            "num_teams": meta.get("num_teams"),
            "playoff_teams": None,
        },
        "teams": teams,
        "matchups": matchups,
    }


def _import_from_sleeper(league_id: str, season: int) -> dict:
    from collections import defaultdict

    from ffpy.draft_strategy import load_sleeper_players

    league = SleeperIntegration.get_league(league_id)
    rosters = SleeperIntegration.get_rosters(league_id)
    users = SleeperIntegration.get_league_users(league_id)
    user_by_id = {u.get("user_id"): u for u in users}
    players_map = load_sleeper_players()

    teams = []
    for r in rosters:
        roster_id = r.get("roster_id")
        owner_id = r.get("owner_id") or ""
        user = user_by_id.get(owner_id, {})
        metadata = user.get("metadata") or {}
        team_name = (
            metadata.get("team_name")
            or user.get("display_name")
            or (f"Team {roster_id}" if roster_id is not None else "Unknown")
        )
        owner_display = user.get("display_name") or owner_id

        teams.append(
            {
                "team_id": f"sleeper:{league_id}:{roster_id}",
                "name": team_name,
                "owner": owner_display,
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
    return {
        "league": {
            "league_id": f"sleeper:{league_id}",
            "provider": "sleeper",
            "name": league.get("name", "Unknown"),
            "season": league.get("season", season),
            "scoring_type": "custom",
            "roster_size": None,
            "num_teams": league.get("total_rosters"),
            "playoff_teams": league.get("settings", {}).get("playoff_teams"),
        },
        "teams": teams,
        "matchups": matchups,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_league_app(
    db_path: Optional[str] = None,
    *,
    require_auth: Optional[bool] = None,
    auth_verifier: Optional[TokenVerifier] = None,
) -> FastAPI:
    """App factory for the FFPy League Manager."""
    resolved_db_path = db_path or Config.DATABASE_PATH
    static_dir = Path(__file__).parent / "web" / "league_app"
    auth_enabled = Config.WEB_AUTH_ENABLED if require_auth is None else require_auth
    resolved_auth_verifier = auth_verifier or build_token_verifier_from_config()
    if auth_enabled and resolved_auth_verifier is None:
        raise ValueError("Auth is enabled but no token verifier is configured")

    app = FastAPI(
        title="FFPy League Manager",
        version="0.1.0",
        description="FastAPI backend for fantasy league data ingestion and lineup optimization.",
    )
    app.state.db_path = resolved_db_path
    app.state.auth_enabled = auth_enabled

    bearer = HTTPBearer(auto_error=False)

    def get_db() -> FFPyDatabase:
        db = FFPyDatabase(db_path=resolved_db_path)
        try:
            yield db
        finally:
            db.close()

    def get_current_user(
        token: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> AuthenticatedUser:
        if not auth_enabled:
            return AuthenticatedUser(user_id="anon", email=None, role="authenticated", email_confirmed=True, claims={})
        if not token:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        assert resolved_auth_verifier is not None
        try:
            return resolved_auth_verifier.verify_access_token(token.credentials)
        except TokenVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def _get_league_or_404(db: FFPyDatabase, league_id: str, user: AuthenticatedUser) -> dict:
        if not auth_enabled:
            league = db.get_league_by_id(league_id)
        else:
            league = db.get_user_league(league_id, user.user_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        return league

    def _get_teams(db: FFPyDatabase, league_id: str, user: AuthenticatedUser) -> List[dict]:
        if not auth_enabled:
            return db.get_teams_for_league(league_id)
        return db.get_league_teams(league_id, user.user_id)

    def _get_matchups(db: FFPyDatabase, league_id: str, week: int, user: AuthenticatedUser) -> List[dict]:
        if not auth_enabled:
            return db.get_matchups_for_league(league_id, week)
        return db.get_league_matchups(league_id, week, user.user_id)

    # -----------------------------------------------------------------------
    # Static SPA
    # -----------------------------------------------------------------------
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir)), name="league_app_assets")

    @app.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(static_dir / "favicon.ico")

    # -----------------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------------
    @app.get("/api/auth/me")
    def auth_me(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> Dict[str, Any]:
        is_real = auth_enabled and user.user_id != "anon"
        return {
            "authenticated": is_real,
            "auth_required": auth_enabled,
            "user": user.to_dict() if is_real else None,
        }

    @app.get("/api/auth/config")
    def auth_config() -> Dict[str, Any]:
        browser_auth_available = bool(
            auth_enabled and Config.SUPABASE_URL and Config.SUPABASE_BROWSER_KEY
        )
        return {
            "auth_required": auth_enabled,
            "browser_auth_available": browser_auth_available,
            "supabase_url": Config.SUPABASE_URL if browser_auth_available else None,
            "supabase_anon_key": Config.SUPABASE_BROWSER_KEY if browser_auth_available else None,
            "public_app_url": Config.PUBLIC_APP_URL,
        }

    # -----------------------------------------------------------------------
    # Router: Credentials
    # -----------------------------------------------------------------------
    cred_router = APIRouter(prefix="/api/leagues", tags=["credentials"])

    @cred_router.post("/credentials")
    def store_credentials(
        payload: CredentialStoreRequest,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        # Sleeper is public — no secrets to encrypt or persist.
        if payload.provider == "sleeper":
            return {"status": "ok"}
        if not MASTER_KEY:
            raise HTTPException(status_code=500, detail="Encryption key not configured")
        cipher = encrypt_credentials(payload.credentials, user.user_id, MASTER_KEY)
        db.store_user_credentials(user.user_id, payload.provider, cipher, payload.label)
        return {"status": "ok"}

    @cred_router.get("/credentials")
    def list_credentials(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        return db.get_user_credentials(user.user_id)

    @cred_router.delete("/credentials/{provider}")
    def delete_credentials(
        provider: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        db.delete_user_credentials(user.user_id, provider)
        return {"status": "deleted"}

    # -----------------------------------------------------------------------
    # Router: Import
    # -----------------------------------------------------------------------
    import_router = APIRouter(prefix="/api/leagues", tags=["import"])

    @import_router.get("/sleeper/discover")
    def discover_sleeper_leagues(
        username: str,
        season: int = Query(2026, ge=2000, le=2100),
    ) -> List[Dict[str, Any]]:
        """Look up Sleeper leagues for a username (public; no credentials required)."""
        username = username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="username is required")
        try:
            sleeper_user = SleeperIntegration.get_user(username)
            user_id = sleeper_user.get("user_id")
            if not user_id:
                raise HTTPException(status_code=404, detail=f"Sleeper user '{username}' not found")
            leagues = SleeperIntegration.get_user_leagues(str(user_id), season)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Sleeper discover failed for %s", username)
            raise HTTPException(status_code=502, detail=f"Sleeper API error: {exc}") from exc
        return [
            {
                "league_id": lg.get("league_id"),
                "name": lg.get("name"),
                "season": lg.get("season"),
                "status": lg.get("status"),
                "total_rosters": lg.get("total_rosters"),
            }
            for lg in leagues
        ]

    @import_router.post("/import")
    def import_league(
        payload: LeagueImportRequest,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        if payload.provider in ("espn", "yahoo"):
            if not MASTER_KEY:
                raise HTTPException(status_code=500, detail="Encryption key not configured")
            cipher = db.get_credential_ciphertext(user.user_id, payload.provider)
            if not cipher:
                raise HTTPException(status_code=400, detail=f"No stored credentials for {payload.provider}")
            creds = decrypt_credentials(cipher, user.user_id, MASTER_KEY)
        else:
            creds = {}

        if payload.provider == "espn":
            data = _import_from_espn(payload.league_id, payload.season, creds)
        elif payload.provider == "yahoo":
            data = _import_from_yahoo(payload.league_id, payload.season, creds)
        elif payload.provider == "sleeper":
            data = _import_from_sleeper(payload.league_id, payload.season)
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")

        store_user_id = user.user_id
        if payload.provider == "sleeper" and payload.sleeper_username:
            # When auth is off (anon) tie imports to the Sleeper username so
            # draft-help and league lists work without Supabase sign-in.
            name = payload.sleeper_username.strip()
            if name and (not auth_enabled or user.user_id == "anon"):
                store_user_id = name

        league_id = db.store_user_league(store_user_id, data)
        return {"league_id": league_id, "teams": len(data["teams"]), "status": "imported"}

    # -----------------------------------------------------------------------
    # Router: League data
    # -----------------------------------------------------------------------
    league_router = APIRouter(prefix="/api/leagues", tags=["leagues"])

    @league_router.get("")
    def list_leagues(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        if not auth_enabled:
            return db.get_all_leagues()
        return db.get_user_leagues(user.user_id)

    @league_router.get("/{league_id}")
    def get_league(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> dict:
        return _get_league_or_404(db, league_id, user)

    @league_router.get("/{league_id}/teams")
    def get_teams(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        _get_league_or_404(db, league_id, user)
        return _get_teams(db, league_id, user)

    @league_router.get("/{league_id}/matchups/{week}")
    def get_matchups(
        league_id: str,
        week: int,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        _get_league_or_404(db, league_id, user)
        return _get_matchups(db, league_id, week, user)

    @league_router.delete("/{league_id}")
    def delete_league(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        league = _get_league_or_404(db, league_id, user)
        db.delete_user_league(league_id, league["user_id"])
        return {"status": "deleted"}

    @league_router.post("/{league_id}/draft-help")
    def draft_help(
        league_id: str,
        payload: DraftHelpRequest,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        """Return a ranked draft board with reasons for the requesting team."""
        from ffpy.draft_strategy import DraftStrategyConfig, DraftStrategyEngine, load_sleeper_players

        league = _get_league_or_404(db, league_id, user)
        teams = _get_teams(db, league_id, user)
        team = next((t for t in teams if t["team_id"] == payload.team_id), None)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        num_teams = payload.num_teams or int(league.get("num_teams") or 10)
        pick_slots = payload.pick_slots
        if not pick_slots and num_teams:
            # Default snake turn for pick #1 in a 3-round draft.
            pick_slots = [1, 2 * num_teams, 2 * num_teams + 1]

        config = DraftStrategyConfig(num_teams=num_teams, pick_slots=pick_slots)
        engine = DraftStrategyEngine(db, config)
        provider = (league.get("provider") or "").lower()
        sleeper_players = load_sleeper_players() if provider == "sleeper" else None

        try:
            return engine.generate(
                league=league,
                teams=teams,
                my_team_id=payload.team_id,
                num_players=payload.num_players,
                sleeper_players=sleeper_players,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @league_router.post("/{league_id}/optimize")
    def optimize_lineup(
        league_id: str,
        payload: OptimizeRequest,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        """Run lineup optimizer for a league team."""
        from ffpy.optimizer import LineupOptimizer, Player, RosterConstraints

        league = _get_league_or_404(db, league_id, user)
        teams = _get_teams(db, league_id, user)
        team = next((t for t in teams if t["team_id"] == payload.team_id), None)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        roster = json.loads(team.get("roster_json") or "[]")
        if not roster:
            raise HTTPException(status_code=400, detail="Team roster is empty")

        # Parse roster into Player objects
        players = []
        for entry in roster:
            if isinstance(entry, dict):
                name = entry.get("player", entry.get("fullName", "Unknown"))
                position = entry.get("position", "")
                team_abbr = entry.get("team", "")
                proj = entry.get("projected_points", 0.0)
            else:
                name = str(entry)
                position = ""
                team_abbr = ""
                proj = 0.0
            players.append(
                Player(
                    name=name,
                    position=position.upper() if position else "",
                    team=team_abbr,
                    projected_points=float(proj) if proj else 0.0,
                )
            )

        # Build constraints from league settings
        league_settings = json.loads(league.get("league_json") or "{}")
        roster_slots = league_settings.get("roster_slots", {})
        positions = {}
        flex_positions: List[str] = []
        for slot, count in roster_slots.items():
            slot_upper = str(slot).upper()
            if slot_upper == "FLEX":
                flex_positions = ["RB", "WR", "TE"]
                positions["FLEX"] = count
            elif slot_upper == "OP":
                flex_positions = ["QB", "RB", "WR", "TE"]
                positions["OP"] = count
            elif slot_upper not in ("BENCH", "IR"):
                positions[slot_upper] = count

        constraints = RosterConstraints(
            positions=positions,
            flex_positions=flex_positions,
        )

        optimizer = LineupOptimizer(players=players, constraints=constraints)
        best = optimizer.optimize()
        return {
            "total_projected": round(best.total_projected, 2) if best else 0.0,
            "lineup": [
                {
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "projected_points": p.projected_points,
                }
                for p in (best.players if best else [])
            ],
        }

    # -----------------------------------------------------------------------
    # Register routers
    # -----------------------------------------------------------------------
    app.include_router(cred_router)
    app.include_router(import_router)
    app.include_router(league_router)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


def main() -> None:
    """CLI entry point for the league manager web app."""
    parser = argparse.ArgumentParser(description="Run the FFPy League Manager web app.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8001")), help="Port to listen on.")
    parser.add_argument("--db-path", default=None, help="Optional SQLite database path override.")
    args = parser.parse_args()

    app = create_league_app(db_path=args.db_path)
    logger.info(
        "Starting league manager on %s:%s with database=%s auth_enabled=%s",
        args.host,
        args.port,
        app.state.db_path,
        app.state.auth_enabled,
    )
    uvicorn.run(app, host=args.host, port=args.port)


__all__ = ["create_league_app", "main"]
