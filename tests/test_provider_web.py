"""Contract tests for the mountable provider (ESPN) routes — no network."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from ffpy.auth import AuthenticatedUser
from ffpy.database import FFPyDatabase
from ffpy.provider_web import (
    ESPNLeagueIntegration,
    import_from_espn,
    register_provider_routes,
    resolve_credential_master_key,
)

TEST_USER = AuthenticatedUser(
    user_id="dev-user",
    email="dev@local.test",
    role="authenticated",
    email_confirmed=True,
    claims={},
)


@pytest.fixture()
def provider_db(tmp_path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "providers.db"))
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "test-credential-master-key")
    app = FastAPI()
    router = APIRouter(prefix="/api/providers")

    def get_db():
        yield provider_db

    def get_current_user():
        return TEST_USER

    register_provider_routes(router, get_db=get_db, get_current_user=get_current_user)
    app.include_router(router)
    return TestClient(app)


def _auth() -> dict:
    return {"Authorization": "Bearer dev"}


# ---------------------------------------------------------------------------
# master key resolution
# ---------------------------------------------------------------------------


def test_resolve_master_key_prefers_credential_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "explicit-key")
    monkeypatch.setattr("ffpy.provider_web.Config.SUPABASE_JWT_SECRET", "jwt-key")
    assert resolve_credential_master_key() == b"explicit-key"


def test_resolve_master_key_falls_back_to_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "")
    monkeypatch.setattr("ffpy.provider_web.Config.SUPABASE_JWT_SECRET", "jwt-key")
    assert resolve_credential_master_key() == b"jwt-key"


def test_resolve_master_key_empty_when_unconfigured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "")
    monkeypatch.setattr("ffpy.provider_web.Config.SUPABASE_JWT_SECRET", "")
    assert resolve_credential_master_key() == b""


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------


def test_espn_credentials_round_trip(client: TestClient, provider_db: FFPyDatabase):
    resp = client.post(
        "/api/providers/espn/credentials",
        headers=_auth(),
        json={"swid": "{SWID-COOKIE}", "espn_s2": "s2-value", "label": "Work league"},
    )
    assert resp.status_code == 200, resp.text

    listed = client.get("/api/providers/credentials", headers=_auth()).json()
    assert any(c["provider"] == "espn" and c["label"] == "Work league" for c in listed)
    # Ciphertext must never leak through the list endpoint.
    assert all("encrypted" not in c and "swid" not in c for c in listed)

    stored = provider_db.get_credential_ciphertext("dev-user", "espn")
    assert stored and "{SWID-COOKIE}" not in stored

    deleted = client.delete("/api/providers/credentials/espn", headers=_auth())
    assert deleted.status_code == 200
    assert provider_db.get_credential_ciphertext("dev-user", "espn") is None


def test_espn_credentials_require_a_value(client: TestClient):
    resp = client.post("/api/providers/espn/credentials", headers=_auth(), json={"swid": "", "espn_s2": ""})
    assert resp.status_code == 400


def test_delete_credentials_rejects_unknown_provider(client: TestClient):
    resp = client.delete("/api/providers/credentials/sleeper", headers=_auth())
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def _espn_payload(league_id: str = "123", season: int = 2026) -> dict:
    return {
        "league": {
            "league_id": f"espn:{league_id}:{season}",
            "provider": "espn",
            "name": "Test ESPN League",
            "season": season,
            "sleeper_league_id": league_id,
            "scoring_type": "ppr",
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"],
            "num_teams": 10,
        },
        "teams": [
            {"team_id": f"espn:{league_id}:{season}:1", "name": "Team One", "owner": "me", "roster": []},
            {"team_id": f"espn:{league_id}:{season}:2", "name": "Team Two", "owner": "them", "roster": []},
        ],
        "matchups": [],
    }


def _store_espn_credentials(provider_db: FFPyDatabase) -> None:
    from ffpy.league_crypto import encrypt_credentials

    cipher = encrypt_credentials({"swid": "x", "s2": "y"}, "dev-user", b"test-credential-master-key")
    provider_db.store_user_credentials("dev-user", "espn", cipher, "test")


def test_import_requires_credentials(client: TestClient):
    resp = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2026}
    )
    assert resp.status_code == 400
    assert "No stored credentials" in resp.json()["detail"]


def test_import_requires_master_key(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    _store_espn_credentials(provider_db)
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "")
    monkeypatch.setattr("ffpy.provider_web.Config.SUPABASE_JWT_SECRET", "")
    resp = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2026}
    )
    assert resp.status_code == 500
    assert "encryption key" in resp.json()["detail"]


def test_import_rejects_non_numeric_league_id(client: TestClient, provider_db: FFPyDatabase):
    _store_espn_credentials(provider_db)
    resp = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "abc", "season": 2026}
    )
    assert resp.status_code == 400


def test_import_failure_maps_to_502(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    _store_espn_credentials(provider_db)

    def boom(*args, **kwargs):
        raise RuntimeError("espn down")

    monkeypatch.setattr("ffpy.provider_web.import_from_espn", boom)
    resp = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2026}
    )
    assert resp.status_code == 502


def test_espn_import_creates_franchise_and_season(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    _store_espn_credentials(provider_db)
    monkeypatch.setattr("ffpy.provider_web.import_from_espn", lambda *a, **k: _espn_payload())

    resp = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2026}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["league_id"] == "espn:123:2026"
    assert body["franchise_id"] == "franchise:dev-user:espn:123"
    assert body["teams"] == 2
    assert body["status"] == "imported"

    # Franchise surfaces the season for the franchise-centric UI.
    franchises = provider_db.list_franchises("dev-user")
    espn_franchises = [f for f in franchises if f["franchise_id"] == "franchise:dev-user:espn:123"]
    assert len(espn_franchises) == 1
    seasons = espn_franchises[0]["seasons"]
    assert [s["league_id"] for s in seasons] == ["espn:123:2026"]
    assert seasons[0]["sleeper_league_id"] == "123"

    league = provider_db.get_user_league("espn:123:2026", "dev-user")
    assert league and league["provider"] == "espn"
    teams = provider_db.get_league_teams("espn:123:2026", "dev-user")
    assert len(teams) == 2


def test_espn_import_second_season_same_league(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    _store_espn_credentials(provider_db)
    monkeypatch.setattr("ffpy.provider_web.import_from_espn", lambda *a, **k: _espn_payload())

    first = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2026}
    )
    assert first.status_code == 200, first.text
    monkeypatch.setattr("ffpy.provider_web.import_from_espn", lambda *a, **k: _espn_payload(season=2025))
    second = client.post(
        "/api/providers/espn/import", headers=_auth(), json={"league_id": "123", "season": 2025}
    )
    assert second.status_code == 200, second.text
    assert second.json()["league_id"] == "espn:123:2025"

    # Two seasons of the same ESPN league share one franchise without clobbering.
    seasons = provider_db.get_franchise_leagues("franchise:dev-user:espn:123", "dev-user")
    assert {s["league_id"] for s in seasons} == {"espn:123:2025", "espn:123:2026"}


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def _seed_imported_espn_league(provider_db: FFPyDatabase) -> None:
    provider_db.store_user_league("dev-user", _espn_payload(), franchise_id="franchise:dev-user:espn:123")


def test_refresh_unknown_league_404(client: TestClient):
    resp = client.post("/api/providers/leagues/espn:999:2026/refresh", headers=_auth())
    assert resp.status_code == 404


def test_refresh_reimports_with_stored_credentials(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
):
    _seed_imported_espn_league(provider_db)
    _store_espn_credentials(provider_db)
    monkeypatch.setattr("ffpy.provider_web.import_from_espn", lambda *a, **k: _espn_payload())

    resp = client.post("/api/providers/leagues/espn:123:2026/refresh", headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "refreshed"
    assert body["league_id"] == "espn:123:2026"
    assert body["teams"] == 2


def test_refresh_rejects_sleeper_leagues(client: TestClient, provider_db: FFPyDatabase):
    provider_db.store_user_league(
        "dev-user",
        {
            "league": {
                "league_id": "sleeper:123:2026",
                "provider": "sleeper",
                "name": "Sleeper League",
                "season": 2026,
            },
            "teams": [],
            "matchups": [],
        },
    )
    resp = client.post("/api/providers/leagues/sleeper:123:2026/refresh", headers=_auth())
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# importer payload shape (mocked ESPN integration — no network)
# ---------------------------------------------------------------------------


class _StubESPN:
    def __init__(self, league_id: int, season: int, swid=None, espn_s2=None):
        assert swid == "the-swid"
        assert espn_s2 == "the-s2"

    def get_league_info(self):
        return {
            "name": "Stub ESPN League",
            "size": 10,
            "scoring_type": "PPR",
            "roster_slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "D/ST": 1, "BENCH": 6},
            "playoff_teams": 4,
        }

    def get_all_teams(self):
        return [{"id": 1, "name": "Stub Team", "owner": "stub", "wins": 1, "losses": 0}]

    def get_all_rosters(self):
        import pandas as pd

        return {1: pd.DataFrame([{"player": "Josh Allen", "position": "QB", "team": "BUF"}])}

    def get_matchups(self, week: int):
        return [{"home_team_id": 1, "away_team_id": 2, "home_score": 100, "away_score": 90}]


def test_import_from_espn_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ffpy.provider_web.ESPNLeagueIntegration", _StubESPN)
    data = import_from_espn("123", 2026, {"swid": "the-swid", "s2": "the-s2"})

    assert data["league"]["league_id"] == "espn:123:2026"
    assert data["league"]["sleeper_league_id"] == "123"
    assert data["league"]["scoring_type"] == "ppr"
    # D/ST maps to DEF for starter_slots_from_sleeper; BENCH dropped.
    assert data["league"]["roster_positions"] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
    assert data["teams"][0]["team_id"] == "espn:123:2026:1"
    assert data["teams"][0]["roster"] == [{"player": "Josh Allen", "position": "QB", "team": "BUF"}]
    assert data["matchups"][0]["home_team_id"] == "espn:123:2026:1"
    assert data["matchups"][0]["away_team_id"] == "espn:123:2026:2"
    assert ESPNLeagueIntegration is not None  # symbol still importable for monkeypatching


def test_import_from_espn_empty_roster_is_list(monkeypatch: pytest.MonkeyPatch):
    class _NoRoster(_StubESPN):
        def get_all_rosters(self):
            return {}

    monkeypatch.setattr("ffpy.provider_web.ESPNLeagueIntegration", _NoRoster)
    data = import_from_espn("123", 2026, {"swid": "the-swid", "s2": "the-s2"})
    assert data["teams"][0]["roster"] == []
