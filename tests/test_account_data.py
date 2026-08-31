"""Tests for GDPR user export / purge / feature artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ffpy.account_data import (
    ARTIFACT_CAP_PER_FEATURE,
    delete_feature_artifact,
    expire_feature_artifacts,
    export_user_data,
    list_feature_artifacts,
    purge_user_data,
    save_feature_artifact,
    user_scoped_row_counts,
)
from ffpy.database import FFPyDatabase


@pytest.fixture
def db(tmp_path: Path) -> FFPyDatabase:
    database = FFPyDatabase(db_path=str(tmp_path / "account.db"))
    yield database
    database.close()


def _seed_user(db: FFPyDatabase, user_id: str = "user-1") -> str:
    db.upsert_sleeper_profile(user_id, sleeper_user_id="123", sleeper_username="macker1477")
    franchise = db.upsert_franchise(
        f"franchise:{user_id}",
        user_id,
        display_name="Test Franchise",
        canonical_sleeper_id="123",
    )
    league_id = f"sleeper:league:{user_id}"
    db.store_user_league(
        user_id,
        {
            "league": {
                "league_id": league_id,
                "provider": "sleeper",
                "name": "Test League",
                "season": 2026,
                "scoring_type": "ppr",
                "roster_size": 10,
                "num_teams": 10,
                "franchise_id": franchise["franchise_id"],
                "sleeper_league_id": "999",
                "status": "in_season",
            },
            "teams": [
                {
                    "team_id": f"{league_id}:1",
                    "name": "Team A",
                    "owner": "macker1477",
                    "wins": 1,
                    "losses": 0,
                    "roster": [],
                }
            ],
            "matchups": [
                {
                    "week": 1,
                    "home_team_id": f"{league_id}:1",
                    "away_team_id": f"{league_id}:1",
                    "home_score": 100,
                    "away_score": 90,
                }
            ],
        },
        franchise_id=franchise["franchise_id"],
    )
    db.conn.execute(
        """
        INSERT INTO user_credentials (user_id, provider, encrypted)
        VALUES (?, 'sleeper', 'ciphertext')
        """,
        (user_id,),
    )
    db.conn.commit()
    return league_id


def test_export_user_data_shape(db: FFPyDatabase) -> None:
    league_id = _seed_user(db)
    save_feature_artifact(
        db,
        "user-1",
        feature="draft_help",
        request={"league_id": league_id},
        result={"picks": []},
        league_id=league_id,
        title="Week 0 board",
    )

    payload = export_user_data(db, "user-1", email="user@example.com")
    assert payload["user"] == {"user_id": "user-1", "email": "user@example.com"}
    assert payload["sleeper_profile"]["sleeper_username"] == "macker1477"
    assert len(payload["franchises"]) == 1
    assert len(payload["leagues"]) == 1
    assert payload["leagues"][0]["league"]["league_id"] == league_id
    assert len(payload["leagues"][0]["teams"]) == 1
    assert len(payload["leagues"][0]["matchups"]) == 1
    assert len(payload["feature_artifacts"]) == 1
    assert payload["feature_artifacts"][0]["feature"] == "draft_help"


def test_purge_user_data_removes_all_scoped_rows(db: FFPyDatabase) -> None:
    league_id = _seed_user(db)
    save_feature_artifact(
        db,
        "user-1",
        feature="lineup",
        request={},
        result={"starters": []},
        league_id=league_id,
    )
    other_league = _seed_user(db, user_id="user-2")

    counts = purge_user_data(db, "user-1")
    assert counts["leagues"] == 1
    assert counts["franchises"] == 1
    assert counts["sleeper_profiles"] == 1
    assert counts["credentials"] == 1
    assert counts["feature_artifacts"] == 1
    assert user_scoped_row_counts(db, "user-1") == {
        "user_feature_artifacts": 0,
        "user_leagues": 0,
        "league_franchises": 0,
        "user_sleeper_profiles": 0,
        "user_credentials": 0,
    }
    # Other user's data untouched
    assert db.get_user_league(other_league, "user-2") is not None


def test_artifact_cap_keeps_newest(db: FFPyDatabase) -> None:
    for i in range(ARTIFACT_CAP_PER_FEATURE + 3):
        save_feature_artifact(
            db,
            "user-1",
            feature="trades",
            request={"n": i},
            result={"ok": True},
            title=f"run-{i}",
        )
    rows = list_feature_artifacts(db, "user-1", feature="trades")
    assert len(rows) == ARTIFACT_CAP_PER_FEATURE
    titles = {r["title"] for r in rows}
    assert "run-0" not in titles
    assert f"run-{ARTIFACT_CAP_PER_FEATURE + 2}" in titles


def test_expire_feature_artifacts(db: FFPyDatabase) -> None:
    row = save_feature_artifact(
        db,
        "user-1",
        feature="draft_help",
        request={},
        result={},
        ttl_days=90,
    )
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0)
    past_iso = past.isoformat().replace("+00:00", "Z")
    db.conn.execute(
        "UPDATE user_feature_artifacts SET expires_at = ? WHERE artifact_id = ?",
        (past_iso, row["artifact_id"]),
    )
    db.conn.commit()

    removed = expire_feature_artifacts(db)
    assert removed == 1
    assert list_feature_artifacts(db, "user-1", include_expired=True) == []


def test_delete_feature_artifact(db: FFPyDatabase) -> None:
    row = save_feature_artifact(
        db,
        "user-1",
        feature="lineup",
        request={"week": 1},
        result={"lineup": []},
    )
    assert delete_feature_artifact(db, row["artifact_id"], "user-1") is True
    assert delete_feature_artifact(db, row["artifact_id"], "user-1") is False
