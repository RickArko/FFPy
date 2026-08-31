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


# ---------------------------------------------------------------------------
# Yahoo OAuth (signed state, callback, league discovery, import)
# ---------------------------------------------------------------------------


class _FakeYahoo401(Exception):
    def __init__(self):
        self.response = type("R", (), {"status_code": 401})()


def _configure_yahoo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ffpy.provider_web.Config.YAHOO_CLIENT_ID", "yahoo-client-id")
    monkeypatch.setattr("ffpy.provider_web.Config.YAHOO_CLIENT_SECRET", "yahoo-client-secret")
    monkeypatch.setattr(
        "ffpy.provider_web.Config.YAHOO_REDIRECT_URI",
        "http://localhost:8002/api/providers/yahoo/callback",
    )
    monkeypatch.setattr("ffpy.provider_web.Config.PUBLIC_APP_URL", "http://localhost:8002")


def test_yahoo_authorize_unconfigured_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ffpy.provider_web.Config.YAHOO_CLIENT_ID", "")
    monkeypatch.setattr("ffpy.provider_web.Config.YAHOO_CLIENT_SECRET", "")
    resp = client.get("/api/providers/yahoo/authorize", headers=_auth())
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_yahoo_authorize_returns_consent_url(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.parse as urlparse

    _configure_yahoo(monkeypatch)
    resp = client.get("/api/providers/yahoo/authorize", headers=_auth())
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert "request_auth" in url
    query = urlparse.parse_qs(urlparse.urlparse(url).query)
    assert query["client_id"] == ["yahoo-client-id"]
    assert query["state"], "authorize URL must carry a signed state"


def test_oauth_state_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "test-credential-master-key")
    from ffpy.provider_web import sign_oauth_state, verify_oauth_state

    state = sign_oauth_state("user-abc")
    assert verify_oauth_state(state) == "user-abc"


def test_oauth_state_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "test-credential-master-key")
    from ffpy.provider_web import sign_oauth_state, verify_oauth_state

    state = sign_oauth_state("user-abc")
    assert verify_oauth_state(state[:-2] + "AA") is None
    assert verify_oauth_state("") is None


def test_oauth_state_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ffpy.provider_web.Config.CREDENTIAL_MASTER_KEY", "test-credential-master-key")
    from ffpy.provider_web import sign_oauth_state, verify_oauth_state

    state = sign_oauth_state("user-abc", ttl_seconds=-10)
    assert verify_oauth_state(state) is None


def test_yahoo_callback_stores_tokens(
    client: TestClient,
    provider_db: FFPyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ffpy.league_crypto import decrypt_credentials
    from ffpy.provider_web import sign_oauth_state

    _configure_yahoo(monkeypatch)

    class _Exchange:
        def __init__(self, *args, **kwargs):
            pass

        def exchange_code(self, code: str) -> dict:
            assert code == "the-code"
            return {"access_token": "access-1", "refresh_token": "refresh-1"}

    monkeypatch.setattr("ffpy.provider_web.YahooIntegration", _Exchange)

    state = sign_oauth_state(TEST_USER.user_id)
    resp = client.get(f"/api/providers/yahoo/callback?code=the-code&state={state}", follow_redirects=False)
    assert resp.status_code == 302, resp.text
    assert "yahoo=connected" in resp.headers["location"]

    cipher = provider_db.get_credential_ciphertext(TEST_USER.user_id, "yahoo")
    assert cipher, "callback must store encrypted tokens"
    creds = decrypt_credentials(cipher, TEST_USER.user_id, b"test-credential-master-key")
    assert creds["access_token"] == "access-1"
    assert creds["refresh_token"] == "refresh-1"


def test_yahoo_callback_rejects_bad_state(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_yahoo(monkeypatch)
    resp = client.get("/api/providers/yahoo/callback?code=the-code&state=garbage", follow_redirects=False)
    assert resp.status_code == 302
    assert "yahoo=error" in resp.headers["location"]
    assert provider_db.get_credential_ciphertext(TEST_USER.user_id, "yahoo") is None


def _store_yahoo_tokens(provider_db: FFPyDatabase, access: str, refresh: str) -> None:
    from ffpy.league_crypto import encrypt_credentials

    cipher = encrypt_credentials(
        {"access_token": access, "refresh_token": refresh},
        TEST_USER.user_id,
        b"test-credential-master-key",
    )
    provider_db.store_user_credentials(TEST_USER.user_id, "yahoo", cipher, "Yahoo OAuth tokens")


def test_yahoo_leagues_requires_connection(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_yahoo(monkeypatch)
    resp = client.get("/api/providers/yahoo/leagues", headers=_auth())
    assert resp.status_code == 400
    assert "No stored credentials" in resp.json()["detail"]


def test_yahoo_leagues_refreshes_on_401(
    client: TestClient,
    provider_db: FFPyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ffpy.league_crypto import decrypt_credentials

    _configure_yahoo(monkeypatch)
    _store_yahoo_tokens(provider_db, "access-1", "refresh-1")

    payload = {
        "fantasy_content": {
            "users": {
                "0": {
                    "user": {
                        "games": {
                            "0": {
                                "game": {
                                    "leagues": {
                                        "0": {
                                            "league": [
                                                {
                                                    "league_key": "449.l.123456",
                                                    "name": "Contract Yahoo League",
                                                    "season": "2026",
                                                    "num_teams": 10,
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    calls = {"leagues": 0, "refresh": 0}

    class _Leagues:
        def __init__(self, *args, **kwargs):
            pass

        def get_user_leagues(self, access_token: str, game_key: str = "nfl"):
            calls["leagues"] += 1
            if access_token == "access-1":
                raise _FakeYahoo401()
            assert access_token == "access-2"
            return payload["fantasy_content"]["users"]["0"]["user"]["games"]["0"]["game"]["leagues"]["0"][
                "league"
            ]

        def refresh_access_token(self, refresh_token: str) -> dict:
            calls["refresh"] += 1
            assert refresh_token == "refresh-1"
            return {"access_token": "access-2", "refresh_token": "refresh-2"}

    monkeypatch.setattr("ffpy.provider_web.YahooIntegration", _Leagues)

    resp = client.get("/api/providers/yahoo/leagues", headers=_auth())
    assert resp.status_code == 200, resp.text
    leagues = resp.json()
    assert leagues == [
        {
            "league_key": "449.l.123456",
            "name": "Contract Yahoo League",
            "season": 2026,
            "num_teams": 10,
        }
    ]
    assert calls == {"leagues": 2, "refresh": 1}

    cipher = provider_db.get_credential_ciphertext(TEST_USER.user_id, "yahoo")
    creds = decrypt_credentials(cipher, TEST_USER.user_id, b"test-credential-master-key")
    assert creds["access_token"] == "access-2"
    assert creds["refresh_token"] == "refresh-2"


def test_yahoo_import_validates_league_key(
    client: TestClient, provider_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_yahoo(monkeypatch)
    _store_yahoo_tokens(provider_db, "access-1", "refresh-1")
    resp = client.post(
        "/api/providers/yahoo/import", json={"league_key": "123456", "season": 2026}, headers=_auth()
    )
    assert resp.status_code == 400
    assert "399.l.123456" in resp.json()["detail"]


def test_yahoo_import_creates_franchise(
    client: TestClient,
    provider_db: FFPyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_yahoo(monkeypatch)
    _store_yahoo_tokens(provider_db, "access-1", "refresh-1")

    data = {
        "league": {
            "league_id": "yahoo:449.l.123456:2026",
            "provider": "yahoo",
            "name": "Contract Yahoo League",
            "season": 2026,
            "sleeper_league_id": "449.l.123456",
            "scoring_type": "custom",
            "roster_positions": [],
            "num_teams": 10,
        },
        "teams": [
            {"team_id": "yahoo:449.l.123456:2026:1", "name": "Alpha", "owner": "me", "roster": []},
        ],
        "matchups": [],
    }

    def _import(league_id: str, season: int, creds: dict) -> dict:
        assert creds["access_token"] == "access-1"
        return data

    monkeypatch.setattr("ffpy.provider_web.import_from_yahoo", _import)

    resp = client.post(
        "/api/providers/yahoo/import",
        json={"league_key": "449.l.123456", "season": 2026},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["league_id"] == "yahoo:449.l.123456:2026"
    assert body["franchise_id"] == f"franchise:{TEST_USER.user_id}:yahoo:123456"
    assert body["teams"] == 1

    franchise = provider_db.get_franchise(body["franchise_id"], TEST_USER.user_id)
    assert franchise and franchise["display_name"] == "Contract Yahoo League"


def test_yahoo_refresh_route_retries_on_401(
    client: TestClient,
    provider_db: FFPyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ffpy.league_crypto import decrypt_credentials

    _configure_yahoo(monkeypatch)
    _store_yahoo_tokens(provider_db, "access-1", "refresh-1")

    # Seed a stored yahoo league so the refresh route can find it.
    seeded = {
        "league": {
            "league_id": "yahoo:449.l.123456:2026",
            "provider": "yahoo",
            "name": "Contract Yahoo League",
            "season": 2026,
            "sleeper_league_id": "449.l.123456",
            "scoring_type": "custom",
            "roster_positions": [],
            "num_teams": 10,
        },
        "teams": [],
        "matchups": [],
    }
    provider_db.store_user_league(
        TEST_USER.user_id,
        seeded,
        franchise_id=f"franchise:{TEST_USER.user_id}:yahoo:123456",
    )

    calls = {"imports": 0}

    class _Refresh:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_access_token(self, refresh_token: str) -> dict:
            return {"access_token": "access-2", "refresh_token": "refresh-2"}

    def _import(league_id: str, season: int, creds: dict) -> dict:
        calls["imports"] += 1
        if creds["access_token"] == "access-1":
            raise _FakeYahoo401()
        assert creds["access_token"] == "access-2"
        return seeded

    monkeypatch.setattr("ffpy.provider_web.import_from_yahoo", _import)
    monkeypatch.setattr("ffpy.provider_web.YahooIntegration", _Refresh)

    resp = client.post("/api/providers/leagues/yahoo%3A449.l.123456%3A2026/refresh", headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "refreshed"
    assert calls["imports"] == 2

    cipher = provider_db.get_credential_ciphertext(TEST_USER.user_id, "yahoo")
    creds = decrypt_credentials(cipher, TEST_USER.user_id, b"test-credential-master-key")
    assert creds["access_token"] == "access-2"


def test_yahoo_import_groups_seasons_into_one_franchise(
    client: TestClient,
    provider_db: FFPyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same Yahoo league across seasons (449.l.123 vs 423.l.123) -> one franchise."""

    _configure_yahoo(monkeypatch)
    _store_yahoo_tokens(provider_db, "access-1", "refresh-1")

    def payload(game: str, season: int) -> dict:
        return {
            "league": {
                "league_id": f"yahoo:{game}.l.123456:{season}",
                "provider": "yahoo",
                "name": "Contract Yahoo League",
                "season": season,
                "sleeper_league_id": f"{game}.l.123456",
                "scoring_type": "custom",
                "roster_positions": [],
                "num_teams": 10,
            },
            "teams": [],
            "matchups": [],
        }

    monkeypatch.setattr(
        "ffpy.provider_web.import_from_yahoo", lambda lid, season, creds: payload(lid.split(".")[0], season)
    )

    first = client.post(
        "/api/providers/yahoo/import", json={"league_key": "449.l.123456", "season": 2026}, headers=_auth()
    )
    second = client.post(
        "/api/providers/yahoo/import", json={"league_key": "423.l.123456", "season": 2025}, headers=_auth()
    )
    assert first.status_code == 200 and second.status_code == 200

    franchise_id = f"franchise:{TEST_USER.user_id}:yahoo:123456"
    assert first.json()["franchise_id"] == franchise_id
    assert second.json()["franchise_id"] == franchise_id

    seasons = sorted(
        s["league_id"] for s in provider_db.get_franchise_leagues(franchise_id, TEST_USER.user_id)
    )
    assert seasons == ["yahoo:423.l.123456:2025", "yahoo:449.l.123456:2026"]
