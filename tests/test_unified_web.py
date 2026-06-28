"""Tests for the unified FastAPI web app."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.unified_web import create_unified_app


@pytest.fixture
def api_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "unified-web.db"))
    db.run_migration("002_play_by_play_schema.sql")

    rows = [
        ("2022_01_ARI_KC", 2022, "REG", 1, "2022-09-11", "KC", "ARI", 44, 21, 6.5, 54.0),
        ("2022_01_BUF_NE", 2022, "REG", 1, "2022-09-11", "BUF", "NE", 21, 17, 0.0, 44.0),
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
def client(api_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(Config, "SUPABASE_URL", "")
    monkeypatch.setattr(Config, "SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_ANON_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_BROWSER_KEY", "")
    monkeypatch.setattr(Config, "SUPABASE_JWT_SECRET", "")
    app = create_unified_app(db_path=str(api_db.db_path), require_auth=False)
    with TestClient(app) as test_client:
        yield test_client


def test_root_redirects_to_league(client: TestClient):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/league/"


def test_health_endpoint(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "pickem" in data["services"]
    assert "league" in data["services"]


def test_pickem_frontend_served(client: TestClient):
    res = client.get("/pickem/")
    assert res.status_code == 200
    assert "Pick'em Strategy Tester" in res.text


def test_pickem_assets_served(client: TestClient):
    res = client.get("/pickem/assets/styles.css")
    assert res.status_code == 200
    assert "shell" in res.text


def test_league_frontend_served(client: TestClient):
    res = client.get("/league/")
    assert res.status_code == 200
    assert "FFPy League Manager" in res.text


def test_league_assets_served(client: TestClient):
    res = client.get("/league/assets/styles.css")
    assert res.status_code == 200
    assert "shell" in res.text


def test_pickem_api_strategies(client: TestClient):
    res = client.get("/pickem/api/strategies")
    assert res.status_code == 200
    data = res.json()
    assert "strategies" in data


def test_league_api_auth_config(client: TestClient):
    res = client.get("/league/api/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert data["auth_required"] is False


def test_pickem_backtest_run(client: TestClient):
    res = client.post(
        "/pickem/api/backtests/run",
        json={
            "strategy": {"name": "AllFavorites", "params": {}},
            "season_start": 2022,
            "season_end": 2022,
            "week_start": 1,
            "week_end": 1,
            "season_type": "REG",
            "require_full_coverage": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "weekly_results" in data
