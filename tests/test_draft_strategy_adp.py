"""Tests for draft strategy ADP loading."""

from __future__ import annotations

import pandas as pd
import pytest

from ffpy.database import FFPyDatabase
from ffpy.draft_strategy import DraftStrategyEngine


@pytest.fixture
def api_db(tmp_path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "draft-adp.db"))
    yield db
    db.close()


def test_load_adp_lazy_fetch(api_db: FFPyDatabase, monkeypatch: pytest.MonkeyPatch):
    fake = pd.DataFrame(
        {
            "player_name": ["Alpha RB", "Beta WR"],
            "position": ["RB", "WR"],
            "platform": ["fantasypros", "fantasypros"],
            "adp": [12.0, 24.0],
            "adp_high": [10.0, 20.0],
            "adp_low": [14.0, 28.0],
            "team": ["KC", "MIA"],
        }
    )

    monkeypatch.setattr(
        "ffpy.integrations.adp.fetch_fantasypros_adp",
        lambda season: fake.copy(),
    )

    engine = DraftStrategyEngine(api_db)
    adp, used = engine._load_adp(2026)

    assert used == 2026
    assert len(adp) == 2
    assert len(api_db.get_adp(season=2026, platform="fantasypros")) == 2
