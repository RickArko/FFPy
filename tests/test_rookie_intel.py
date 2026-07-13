"""Tests for rookie intel database CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from ffpy.database import FFPyDatabase


@pytest.fixture
def intel_db(tmp_path: Path) -> FFPyDatabase:
    db = FFPyDatabase(db_path=str(tmp_path / "rookie-intel.db"))
    db.upsert_rookie_watchlist(
        {
            "season": 2026,
            "player_name": "Jeremiyah Love",
            "position": "RB",
            "rank_in_position": 1,
            "adp": 13.8,
            "draft_round": 1,
            "draft_pick": 12,
            "team": "GB",
            "tier": "elite",
            "summary": "First-round Green Bay back with three-down upside.",
        }
    )
    yield db
    db.close()


def test_watchlist_upsert_and_list(intel_db: FFPyDatabase) -> None:
    rows = intel_db.get_rookie_watchlist(2026, position="RB")
    assert len(rows) == 1
    assert rows[0]["player_name"] == "Jeremiyah Love"
    assert rows[0]["tier"] == "elite"


def test_content_publish_workflow(intel_db: FFPyDatabase) -> None:
    draft = intel_db.add_rookie_content(
        {
            "season": 2026,
            "player_name": "Jeremiyah Love",
            "content_type": "analysis",
            "title": "Love landing spot analysis",
            "url": "https://example.com/love",
            "source": "FantasyPros",
            "sentiment": "bullish",
            "summary": "Analysts like the Packers role.",
            "status": "draft",
        }
    )
    assert draft["status"] == "draft"
    assert intel_db.list_rookie_content("Jeremiyah Love", 2026) == []

    published = intel_db.publish_rookie_content(draft["content_id"])
    assert published is not None
    assert published["status"] == "published"
    visible = intel_db.list_rookie_content("Jeremiyah Love", 2026)
    assert len(visible) == 1


def test_review_queue(intel_db: FFPyDatabase) -> None:
    intel_db.add_rookie_content(
        {
            "season": 2026,
            "player_name": "Jeremiyah Love",
            "content_type": "news",
            "title": "Camp note",
            "status": "draft",
        }
    )
    queue = intel_db.list_review_queue(2026)
    assert len(queue) == 1


def test_expert_signals_and_profile(intel_db: FFPyDatabase) -> None:
    content = intel_db.add_rookie_content(
        {
            "season": 2026,
            "player_name": "Jeremiyah Love",
            "content_type": "opinion",
            "title": "Draft range",
            "status": "published",
        }
    )
    intel_db.add_rookie_expert_signal(
        {
            "season": 2026,
            "player_name": "Jeremiyah Love",
            "content_id": content["content_id"],
            "expert_name": "Chris Harris",
            "outlet": "FantasyPros",
            "signal_type": "ppg_range",
            "value_json": {"floor": 14, "ceiling": 20},
        }
    )
    profile = intel_db.get_rookie_profile("Jeremiyah Love", 2026)
    assert profile is not None
    assert profile["content"]
    assert profile["signals"][0]["value_json"]["ceiling"] == 20
