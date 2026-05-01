"""Tests for the FastAPI-backed pick'em strategy tester."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffpy.database import FFPyDatabase
from ffpy.pickem_web import create_app


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
