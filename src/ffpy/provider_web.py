"""Mountable provider (ESPN/Yahoo) routes for franchise-centric web apps.

Promoted from ``league_api.py`` so apps like sleeper-brain can mount
credential storage, league import, and per-season refresh under their own
auth/DI wiring (``get_db`` / ``get_current_user``) without depending on the
standalone FFPy League Manager app.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ffpy.auth import AuthenticatedUser
from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.integrations.yahoo import YahooIntegration
from ffpy.league_crypto import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)

ESPN_FRANCHISE_PREFIX = "espn"
PROVIDER_PATTERN = r"^(espn|yahoo)$"


def resolve_credential_master_key() -> bytes:
    """Master key for credential encryption: CREDENTIAL_MASTER_KEY, else JWT secret.

    The JWT-secret fallback keeps ``make run-auth-local`` (local HS256 auth)
    working without a separate key; production sets CREDENTIAL_MASTER_KEY.
    """

    key = Config.CREDENTIAL_MASTER_KEY or Config.SUPABASE_JWT_SECRET
    return key.encode() if key else b""


# ---------------------------------------------------------------------------
# Shared importers (provider payload -> store_user_league shape)
# ---------------------------------------------------------------------------


def import_from_espn(league_id: str, season: int, creds: dict) -> dict:
    """Import an ESPN league as a season-qualified payload.

    Stored league/team ids follow the Sleeper convention
    (``espn:{league_id}:{season}``) so multiple seasons of the same league
    don't clobber each other and the franchise UI can group them.
    """

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
                        "home_team_id": f"espn:{league_id}:{season}:{m['home_team_id']}",
                        "away_team_id": f"espn:{league_id}:{season}:{m['away_team_id']}",
                        "home_score": m.get("home_score"),
                        "away_score": m.get("away_score"),
                        "is_playoff": 0,
                        "is_consolation": 0,
                    }
                )
        except Exception:
            # ESPN returns empty schedule for future weeks; stop at the first failure
            break

    team_list = []
    for t in teams:
        team_id = t["id"]
        roster = all_rosters.get(team_id)
        team_list.append(
            {
                "team_id": f"espn:{league_id}:{season}:{team_id}",
                "name": t["name"],
                "owner": t.get("owner", "Unknown"),
                "wins": t.get("wins", 0),
                "losses": t.get("losses", 0),
                "ties": t.get("ties", 0),
                "points_for": t.get("points_for", 0),
                "points_against": t.get("points_against", 0),
                "rank": t.get("rank"),
                "roster": roster.to_dict(orient="records") if roster is not None and not roster.empty else [],
            }
        )

    roster_positions: List[str] = []
    for slot, count in (info.get("roster_slots") or {}).items():
        label = str(slot).upper()
        if label in ("BENCH", "IR"):
            continue
        mapped = "DEF" if label in ("D/ST", "DST") else label
        roster_positions.extend([mapped] * int(count))

    return {
        "league": {
            "league_id": f"espn:{league_id}:{season}",
            "provider": "espn",
            "name": info.get("name", "Unknown"),
            "season": season,
            "sleeper_league_id": str(league_id),
            "scoring_type": info.get("scoring_type", "custom").lower().replace("-", "_"),
            "roster_positions": roster_positions,
            "roster_size": info.get("size"),
            "num_teams": info.get("size"),
            "playoff_teams": info.get("playoff_teams"),
        },
        "teams": team_list,
        "matchups": matchups,
    }


def import_from_yahoo(league_id: str, season: int, creds: dict) -> dict:
    """Import a Yahoo league as a season-qualified payload."""

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
                "team_id": f"yahoo:{league_id}:{season}:{team_key}",
                "name": s.get("name", "Unknown"),
                "owner": s.get("manager", {}).get("nickname", "Unknown"),
                "wins": s.get("standings", {}).get("outcome_totals", {}).get("wins", 0),
                "losses": s.get("standings", {}).get("outcome_totals", {}).get("losses", 0),
                "ties": s.get("standings", {}).get("outcome_totals", {}).get("ties", 0),
                "points_for": s.get("standings", {}).get("points_for", 0),
                "points_against": s.get("standings", {}).get("points_against", 0),
                "rank": s.get("rank"),
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
                            "home_team_id": f"yahoo:{league_id}:{season}:{home}",
                            "away_team_id": f"yahoo:{league_id}:{season}:{away}",
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
            "league_id": f"yahoo:{league_id}:{season}",
            "provider": "yahoo",
            "name": meta.get("name", "Unknown"),
            "season": season,
            "sleeper_league_id": str(league_id),
            "scoring_type": "custom",
            "roster_positions": [],
            "roster_size": None,
            "num_teams": meta.get("num_teams"),
            "playoff_teams": None,
        },
        "teams": teams,
        "matchups": matchups,
    }


# ---------------------------------------------------------------------------
# Route bodies
# ---------------------------------------------------------------------------


class EspnCredentialBody(BaseModel):
    swid: str = Field("", max_length=128)
    espn_s2: str = Field("", max_length=512)
    label: str = Field("", max_length=128)


class EspnImportBody(BaseModel):
    league_id: str = Field(..., min_length=1, max_length=32)
    season: int = Field(..., ge=2000, le=2100)


class ProviderImportRequest(BaseModel):
    """Generic provider import (Yahoo, Phase 3): league id + season.

    Credentials are read from the encrypted store; ``credentials`` allows an
    explicit access token for CLI-style flows without stored credentials.
    """

    league_id: str = Field(..., min_length=1, max_length=64)
    season: int = Field(..., ge=2000, le=2100)
    credentials: Dict[str, Any] = Field(default_factory=dict)


def _require_master_key() -> bytes:
    master = resolve_credential_master_key()
    if not master:
        raise HTTPException(status_code=500, detail="Credential encryption key not configured")
    return master


def _load_credentials(db: FFPyDatabase, user_id: str, provider: str, master: bytes) -> dict:
    cipher = db.get_credential_ciphertext(user_id, provider)
    if not cipher:
        raise HTTPException(status_code=400, detail=f"No stored credentials for {provider}")
    return decrypt_credentials(cipher, user_id, master)


def _import_with_franchise(
    db: FFPyDatabase,
    user_id: str,
    provider: str,
    data: dict,
    *,
    franchise_key: str,
) -> Dict[str, Any]:
    """Auto-create a single-season franchise and store the imported league."""

    league = data["league"]
    franchise_id = f"franchise:{user_id}:{franchise_key}"
    db.upsert_franchise(
        franchise_id,
        user_id,
        display_name=league.get("name") or "Unknown League",
        canonical_sleeper_id=None,
    )
    league["franchise_id"] = franchise_id
    stored_league_id = db.store_user_league(user_id, data, franchise_id=franchise_id)
    db.reassign_franchise_leagues(user_id, franchise_id)
    franchise = db.get_franchise(franchise_id, user_id)
    return {
        "league_id": stored_league_id,
        "franchise_id": franchise_id,
        "franchise": franchise,
        "teams": len(data.get("teams", [])),
        "status": "imported",
    }


# ---------------------------------------------------------------------------
# Mountable router
# ---------------------------------------------------------------------------


def register_provider_routes(
    router: APIRouter,
    *,
    get_db,
    get_current_user,
) -> None:
    """Register provider credential/import/refresh routes on ``router``."""

    @router.post("/espn/credentials")
    def store_espn_credentials(
        payload: EspnCredentialBody,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        if not (payload.swid.strip() or payload.espn_s2.strip()):
            raise HTTPException(status_code=400, detail="Provide swid and/or espn_s2 cookies")
        master = _require_master_key()
        creds = {"swid": payload.swid.strip(), "s2": payload.espn_s2.strip()}
        cipher = encrypt_credentials(creds, user.user_id, master)
        db.store_user_credentials(user.user_id, "espn", cipher, payload.label)
        return {"status": "ok"}

    @router.get("/credentials")
    def list_credentials(
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> List[dict]:
        return db.get_user_credentials(user.user_id)

    @router.delete("/credentials/{provider}")
    def delete_credentials(
        provider: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, str]:
        if provider not in ("espn", "yahoo"):
            raise HTTPException(status_code=400, detail="Unsupported provider")
        db.delete_user_credentials(user.user_id, provider)
        return {"status": "deleted"}

    @router.post("/espn/import")
    def import_espn_league(
        payload: EspnImportBody,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        master = _require_master_key()
        creds = _load_credentials(db, user.user_id, "espn", master)
        league_id = payload.league_id.strip()
        if not league_id.isdigit():
            raise HTTPException(status_code=400, detail="ESPN league ID must be numeric")
        try:
            data = import_from_espn(league_id, payload.season, creds)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("ESPN import failed league_id=%s season=%s", league_id, payload.season)
            raise HTTPException(
                status_code=502,
                detail="ESPN import failed. Check the league ID, season, and cookie values, then try again.",
            ) from exc
        result = _import_with_franchise(
            db,
            user.user_id,
            "espn",
            data,
            franchise_key=f"espn:{league_id}",
        )
        return result

    @router.post("/leagues/{league_id}/refresh")
    def refresh_provider_league(
        league_id: str,
        user: AuthenticatedUser = Depends(get_current_user),
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        league = db.get_user_league(league_id, user.user_id)
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        provider = league.get("provider") or ""
        season = int(league.get("season") or 0)
        if not season:
            raise HTTPException(status_code=400, detail="League row is missing a season")
        raw_id = league.get("sleeper_league_id") or league_id.split(":", 1)[-1]
        if provider == "espn":
            master = _require_master_key()
            creds = _load_credentials(db, user.user_id, "espn", master)
            try:
                data = import_from_espn(str(raw_id), season, creds)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("ESPN refresh failed league_id=%s", league_id)
                raise HTTPException(
                    status_code=502,
                    detail="ESPN refresh failed. Check your stored cookies and try again.",
                ) from exc
        elif provider == "yahoo":
            master = _require_master_key()
            creds = _load_credentials(db, user.user_id, "yahoo", master)
            try:
                data = import_from_yahoo(str(raw_id), season, creds)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Yahoo refresh failed league_id=%s", league_id)
                raise HTTPException(
                    status_code=502,
                    detail="Yahoo refresh failed. Reconnect Yahoo and try again.",
                ) from exc
        else:
            raise HTTPException(
                status_code=400, detail=f"Provider '{provider}' does not support refresh here"
            )

        franchise_id = league.get("franchise_id")
        data["league"]["franchise_id"] = franchise_id
        db.store_user_league(user.user_id, data, franchise_id=franchise_id)
        if franchise_id:
            db.reassign_franchise_leagues(user.user_id, franchise_id)
        return {"status": "refreshed", "league_id": league_id, "teams": len(data.get("teams", []))}


__all__ = [
    "EspnCredentialBody",
    "EspnImportBody",
    "ProviderImportRequest",
    "import_from_espn",
    "import_from_yahoo",
    "register_provider_routes",
    "resolve_credential_master_key",
]
