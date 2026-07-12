"""Tests for rookie projection helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ffpy.database import FFPyDatabase
from ffpy.rookie_projections import draft_capital_ppg, market_curve_ppg, project


@pytest.fixture
def rookie_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "rookie-proj.db"))
    db.conn.execute(
        "INSERT INTO players (player_id, name, nfl_id, team, position) VALUES (1, 'Jeremiyah Love', 'gsis-1', 'GB', 'RB')"
    )
    db.conn.execute(
        """
        INSERT INTO player_rosters
          (gsis_id, player_name, season, team, position, years_exp, draft_round, draft_pick)
        VALUES ('gsis-1', 'Jeremiyah Love', 2026, 'GB', 'RB', 0, 1, 12)
        """
    )
    db.conn.commit()
    yield db
    db.close()


def test_market_curve_declines_with_rank() -> None:
    assert market_curve_ppg("RB", 1) > market_curve_ppg("RB", 14)


def test_draft_capital_fallback_for_first_round_rb(tmp_path: Path) -> None:
    db = FFPyDatabase(db_path=str(tmp_path / "empty-rookie.db"))
    try:
        assert draft_capital_ppg(db, "RB", 1) == 19.5
    finally:
        db.close()


def test_project_uses_draft_capital(rookie_db: FFPyDatabase) -> None:
    result = project(
        rookie_db,
        name="Jeremiyah Love",
        position="RB",
        adp_rank=14,
        pos_rank=3,
        season=2026,
    )
    assert result.ppg >= 16.0
    assert result.floor_ppg < result.ppg < result.ceiling_ppg
