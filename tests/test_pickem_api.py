"""Tests for the FastAPI-backed pick'em strategy tester."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from ffpy.auth import SupabaseTokenVerifier
from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.pickem_web import create_app
from ffpy.usage_logging import InMemoryUsageEventLogger


@pytest.fixture
def api_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "pickem-api.db"))
    db.run_migration("002_play_by_play_schema.sql")

    rows = [
        ("2022_01_ARI_KC", 2022, "REG", 1, "2022-09-11", "KC", "ARI", 44, 21, 6.5, 54.0),
        ("2022_01_NYG_TEN", 2022, "REG", 1, "2022-09-11", "TEN", "NYG", 20, 21, 5.5, 43.5),
        ("2022_01_LAC_LV", 2022, "REG", 1, "2022-09-11", "LV", "LAC", 19, 24, -3.0, 52.5),
        ("2022_01_BUF_NE", 2022, "REG", 1, "2022-09-11", "BUF", "NE", 21, 17, 0.0, 44.0),
        ("2022_02_NYG_DAL", 2022, "REG", 2, "2022-09-18", "DAL", "NYG", 28, 14, 7.0, 45.0),
        ("2022_02_SF_SEA", 2022, "REG", 2, "2022-09-18", "SEA", "SF", 17, 27, -10.0, 41.5),
        ("2022_02_IND_NYG", 2022, "REG", 2, "2022-09-18", "NYG", "IND", 20, 20, 3.0, 45.5),
    ]

    db.conn.cursor().executemany(
        """INSERT INTO games (game_id, season, season_type, week, game_date,
                              home_team, away_team, home_score, away_score,
                              spread_line, total_line, game_finished)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        rows,
    )
    db.conn.commit()

    yield db
    db.close()


@pytest.fixture
def client(api_db: FFPyDatabase) -> TestClient:
    app = create_app(db_path=str(api_db.db_path))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_secret() -> str:
    return "super-secret-test-key-with-32-bytes"


@pytest.fixture
def auth_verifier(auth_secret: str) -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(
        jwt_secret=auth_secret,
        audience="authenticated",
        fetch_user_on_verify=False,
    )


@pytest.fixture
def usage_logger() -> InMemoryUsageEventLogger:
    return InMemoryUsageEventLogger()


@pytest.fixture
def auth_client(
    api_db: FFPyDatabase,
    auth_verifier: SupabaseTokenVerifier,
    usage_logger: InMemoryUsageEventLogger,
) -> TestClient:
    app = create_app(
        db_path=str(api_db.db_path),
        require_auth=True,
        auth_verifier=auth_verifier,
        usage_logger=usage_logger,
    )
    with TestClient(app) as test_client:
        yield test_client


def _make_access_token(
    secret: str,
    *,
    email_confirmed: bool,
    role: str = "authenticated",
) -> str:
    now = datetime.now(tz=timezone.utc)
    claims = {
        "sub": "72e6cadc-8476-4db1-9d68-b5c0a1982f0f",
        "email": "demo@example.com",
        "role": role,
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    if email_confirmed:
        claims["email_confirmed_at"] = now.isoformat()
    return jwt.encode(claims, secret, algorithm="HS256")


def test_root_serves_frontend(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Pick'em Strategy Tester" in response.text


def test_strategies_endpoint_lists_supported_strategies(client: TestClient):
    response = client.get("/api/strategies")
    assert response.status_code == 200

    strategies = response.json()["strategies"]
    names = {strategy["name"] for strategy in strategies}

    assert {"AllFavorites", "ConfidenceBySpread", "HomeBoost", "UnderdogTargeted", "WinProbBlend"} <= names


def test_coverage_endpoint_reports_default_window(client: TestClient):
    response = client.get("/api/coverage")
    assert response.status_code == 200

    payload = response.json()
    assert payload["default_window"]["season_start"] == 2022
    assert payload["default_window"]["week_end"] == 2
    assert payload["season_summaries"][0]["fully_usable_weeks"] == [1, 2]


def test_run_backtest_returns_summary_and_weekly_results(client: TestClient):
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy": {"name": "AllFavorites", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
            "persist": False,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["summary"]["correct"] == 5
    assert payload["summary"]["incorrect"] == 1
    assert payload["summary"]["ties"] == 1
    assert len(payload["weekly_results"]) == 2
    assert payload["weekly_results"][0]["week"] == 1


def test_compare_backtests_returns_ranked_leaderboard(client: TestClient):
    response = client.post(
        "/api/backtests/compare",
        json={
            "strategies": [
                {"name": "AllFavorites", "params": {}},
                {"name": "HomeBoost", "params": {"threshold": 3.0}},
            ],
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
        },
    )
    assert response.status_code == 200

    leaderboard = response.json()["leaderboard"]
    assert len(leaderboard) == 2
    assert leaderboard[0]["strategy"] == "AllFavorites"
    assert leaderboard[0]["win_rate"] >= leaderboard[1]["win_rate"]


def test_run_backtest_rejects_unknown_strategy(client: TestClient):
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy": {"name": "MysteryBall", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
            "persist": False,
        },
    )
    assert response.status_code == 400
    assert "Unknown strategy" in response.json()["detail"]


def test_auth_config_reports_open_local_mode(client: TestClient):
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_required"] is False
    assert payload["browser_auth_available"] is False
    assert payload["supabase_url"] is None
    assert payload["supabase_anon_key"] is None


def test_auth_config_exposes_public_supabase_settings_for_browser_sign_in(
    api_db: FFPyDatabase,
    auth_verifier: SupabaseTokenVerifier,
    usage_logger: InMemoryUsageEventLogger,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(Config, "SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setattr(Config, "SUPABASE_ANON_KEY", "anon-demo-key")
    monkeypatch.setattr(Config, "PUBLIC_APP_URL", "http://localhost:8000")

    app = create_app(
        db_path=str(api_db.db_path),
        require_auth=True,
        auth_verifier=auth_verifier,
        usage_logger=usage_logger,
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/auth/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_required"] is True
    assert payload["browser_auth_available"] is True
    assert payload["supabase_url"] == "https://demo.supabase.co"
    assert payload["supabase_anon_key"] == "anon-demo-key"
    assert payload["public_app_url"] == "http://localhost:8000"


def test_auth_me_reports_auth_requirement(auth_client: TestClient):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_required"] is True
    assert payload["authenticated"] is False


def test_protected_run_requires_auth_when_enabled(
    auth_client: TestClient,
    usage_logger: InMemoryUsageEventLogger,
):
    response = auth_client.post(
        "/api/backtests/run",
        json={
            "strategy": {"name": "AllFavorites", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
            "persist": False,
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert usage_logger.events[-1].denied_reason == "missing_bearer_token"


def test_protected_run_requires_verified_email(
    auth_client: TestClient,
    auth_secret: str,
    usage_logger: InMemoryUsageEventLogger,
):
    token = _make_access_token(auth_secret, email_confirmed=False)
    response = auth_client.post(
        "/api/backtests/run",
        json={
            "strategy": {"name": "AllFavorites", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
            "persist": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Verified email required"
    assert usage_logger.events[-1].denied_reason == "email_not_verified"


def test_verified_user_can_run_protected_backtest(
    auth_client: TestClient,
    auth_secret: str,
    usage_logger: InMemoryUsageEventLogger,
):
    token = _make_access_token(auth_secret, email_confirmed=True)
    response = auth_client.post(
        "/api/backtests/run",
        json={
            "strategy": {"name": "AllFavorites", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 2,
            "season_type": "REG",
            "require_full_coverage": True,
            "persist": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["correct"] == 5
    assert usage_logger.events[-1].success is True
