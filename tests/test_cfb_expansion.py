"""Tests for CFB college expansion (settings, draft, waivers, trades, playoffs)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ffpy.database import FFPyDatabase
from ffpy.league_api import create_league_app


def _seed_expansion_db(db_path):
    db = FFPyDatabase(str(db_path))
    db.store_cfb_teams(
        pd.DataFrame(
            [
                {
                    "team_key": "alabama",
                    "season": 2024,
                    "school": "Alabama",
                    "conference": "SEC",
                    "abbreviation": "ALA",
                },
                {
                    "team_key": "georgia",
                    "season": 2024,
                    "school": "Georgia",
                    "conference": "SEC",
                    "abbreviation": "UGA",
                },
                {
                    "team_key": "ohio_state",
                    "season": 2024,
                    "school": "Ohio State",
                    "conference": "Big Ten",
                    "abbreviation": "OSU",
                },
                {
                    "team_key": "clemson",
                    "season": 2024,
                    "school": "Clemson",
                    "conference": "ACC",
                    "abbreviation": "CLEM",
                },
            ]
        )
    )
    db.seed_cfb_dst_players(2024, conferences=["SEC", "Big Ten", "ACC"])
    players_data = [
        ("Jalen Milroe", "QB", "alabama", "SEC", 4432577),
        ("Carson Beck", "QB", "georgia", "SEC", 4432580),
        ("Big Ten QB", "QB", "ohio_state", "Big Ten", 999),
        ("ACC QB", "QB", "clemson", "ACC", 998),
        ("RB One", "RB", "alabama", "SEC", 4432578),
        ("RB Two", "RB", "georgia", "SEC", 4432579),
        ("WR One", "WR", "alabama", "SEC", 4432581),
        ("WR Two", "WR", "georgia", "SEC", 4432582),
    ]
    for i in range(100, 180):
        players_data.append((f"Player {i}", "WR", "alabama", "SEC", 500000 + i))
    db.store_cfb_players(
        pd.DataFrame(
            [
                {
                    "season": 2024,
                    "full_name": name,
                    "position": pos,
                    "team_key": tk,
                    "conference": conf,
                    "cfbd_athlete_id": aid,
                    "conference_eligible": 1,
                    "fantasy_eligible": 1,
                }
                for name, pos, tk, conf, aid in players_data
            ]
        ),
        season=2024,
    )
    players = db.get_cfb_players(season=2024)
    pids = {row["full_name"]: int(row["player_id"]) for _, row in players.iterrows()}
    for pid in pids.values():
        db.store_cfb_projections(
            pd.DataFrame(
                [
                    {
                        "player_id": pid,
                        "season": 2024,
                        "week": 1,
                        "model": "historical",
                        "projected_points": 20.0,
                    }
                ]
            )
        )
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db.conn.execute(
        """
        INSERT INTO cfb_game_locks (game_id, season, week, team_key, lock_time_utc)
        VALUES ('g1', 2024, 1, 'alabama', ?)
        ON CONFLICT(game_id, team_key) DO UPDATE SET lock_time_utc = excluded.lock_time_utc
        """,
        (past,),
    )
    db.conn.commit()
    db.close()
    return pids


@pytest.fixture()
def expansion_db(tmp_path):
    db_path = tmp_path / "cfb-expansion.db"
    pids = _seed_expansion_db(db_path)
    return db_path, pids


@pytest.fixture()
def expansion_client(expansion_db):
    db_path, _ = expansion_db
    app = create_league_app(db_path=str(db_path), require_auth=False)
    return TestClient(app)


def _create_league(client, num_teams=4):
    resp = client.post(
        "/api/cfb/leagues",
        json={"name": "Expansion League", "season": 2024, "num_teams": num_teams},
    )
    assert resp.status_code == 200
    return resp.json()["league_id"]


def _create_teams(client, league_id, names):
    ids = []
    for name in names:
        r = client.post(f"/api/cfb/leagues/{league_id}/teams", json={"team_name": name})
        assert r.status_code == 200, r.text
        ids.append(r.json()["league_team_id"])
    return ids


def test_league_settings_patch(expansion_client):
    league_id = _create_league(expansion_client)
    detail = expansion_client.get(f"/api/cfb/leagues/{league_id}")
    assert detail.status_code == 200
    assert detail.json()["settings"]["faab_budget"] == 100

    patch = expansion_client.patch(
        f"/api/cfb/leagues/{league_id}",
        json={"faab_budget": 200, "waiver_type": "faab"},
    )
    assert patch.status_code == 200
    assert patch.json()["settings"]["faab_budget"] == 200


def test_dst_in_player_pool(expansion_client, expansion_db):
    _, pids = expansion_db
    league_id = _create_league(expansion_client)
    pool = expansion_client.get(f"/api/cfb/leagues/{league_id}/player-pool")
    dst_players = [p for p in pool.json()["players"] if p.get("position") == "DST"]
    assert len(dst_players) >= 4
    assert any("Alabama" in p["full_name"] for p in dst_players)


def test_lineup_lock_rejects_locked_player(expansion_client, expansion_db):
    _, pids = expansion_db
    league_id = _create_league(expansion_client)
    team_id = _create_teams(expansion_client, league_id, ["Lock Team"])[0]
    milroe = pids["Jalen Milroe"]
    resp = expansion_client.post(
        f"/api/cfb/leagues/{league_id}/teams/{team_id}/lineup",
        json={
            "season": 2024,
            "week": 1,
            "entries": [{"player_id": milroe, "slot": "QB", "is_starter": True}],
        },
    )
    assert resp.status_code == 400
    assert "locked" in resp.json()["detail"].lower()


def test_snake_draft_completes(expansion_client, expansion_db):
    league_id = _create_league(expansion_client)
    _create_teams(expansion_client, league_id, ["T1", "T2", "T3", "T4"])

    start = expansion_client.post(f"/api/cfb/leagues/{league_id}/draft/start")
    assert start.status_code == 200
    board = start.json()
    assert board["status"] == "active"

    db = FFPyDatabase(str(expansion_client.app.state.db_path))
    pool = db.get_cfb_players(season=2024, conferences=["SEC", "Big Ten", "ACC"], fantasy_eligible=True)
    available = pool["player_id"].tolist()
    db.close()

    picks_made = 0
    while picks_made < board["total_picks"]:
        b = expansion_client.get(f"/api/cfb/leagues/{league_id}/draft").json()
        if b["status"] != "active":
            break
        pid = available[picks_made % len(available)]
        resp = expansion_client.post(
            f"/api/cfb/leagues/{league_id}/draft/pick",
            json={"player_id": int(pid)},
        )
        assert resp.status_code == 200, resp.text
        picks_made += 1

    final = expansion_client.get(f"/api/cfb/leagues/{league_id}/draft").json()
    assert final["status"] == "complete"
    rosters = expansion_client.get(f"/api/cfb/leagues/{league_id}/teams")
    total_rostered = sum(len(t["roster"]) for t in rosters.json())
    assert total_rostered == final["total_picks"]


def test_duplicate_draft_pick_rejected(expansion_client):
    league_id = _create_league(expansion_client)
    _create_teams(expansion_client, league_id, ["A", "B", "C", "D"])
    expansion_client.post(f"/api/cfb/leagues/{league_id}/draft/start")

    db = FFPyDatabase(str(expansion_client.app.state.db_path))
    pid = int(db.get_cfb_players(season=2024).iloc[0]["player_id"])
    db.close()

    first = expansion_client.post(f"/api/cfb/leagues/{league_id}/draft/pick", json={"player_id": pid})
    assert first.status_code == 200
    second = expansion_client.post(f"/api/cfb/leagues/{league_id}/draft/pick", json={"player_id": pid})
    assert second.status_code == 400


def test_faab_waiver_highest_bid_wins(expansion_client, expansion_db):
    _, pids = expansion_db
    league_id = _create_league(expansion_client)
    t1, t2 = _create_teams(expansion_client, league_id, ["Bid A", "Bid B"])
    target = pids["ACC QB"]

    expansion_client.post(
        f"/api/cfb/leagues/{league_id}/transactions",
        json={
            "league_team_id": t1,
            "tx_type": "add",
            "player_id": target,
            "faab_bid": 10,
            "week": 2,
        },
    )
    expansion_client.post(
        f"/api/cfb/leagues/{league_id}/transactions",
        json={
            "league_team_id": t2,
            "tx_type": "add",
            "player_id": target,
            "faab_bid": 25,
            "week": 2,
        },
    )
    run = expansion_client.post(
        f"/api/cfb/leagues/{league_id}/waiver-run",
        json={"week": 2},
    )
    assert run.status_code == 200
    assert run.json()["processed"] == 1

    roster_b = expansion_client.get(f"/api/cfb/leagues/{league_id}/teams/{t2}/roster").json()["roster"]
    assert any(r["player_id"] == target for r in roster_b)


def test_trade_swap_players(expansion_client, expansion_db):
    _, pids = expansion_db
    league_id = _create_league(expansion_client)
    t1, t2 = _create_teams(expansion_client, league_id, ["Trade A", "Trade B"])
    p1, p2 = pids["Jalen Milroe"], pids["Carson Beck"]

    expansion_client.post(f"/api/cfb/leagues/{league_id}/teams/{t1}/roster", json={"add": [p1], "drop": []})
    expansion_client.post(f"/api/cfb/leagues/{league_id}/teams/{t2}/roster", json={"add": [p2], "drop": []})

    trade = expansion_client.post(
        f"/api/cfb/leagues/{league_id}/trades",
        json={
            "proposer_team_id": t1,
            "recipient_team_id": t2,
            "items": [
                {"player_id": p1, "from_team_id": t1, "to_team_id": t2},
                {"player_id": p2, "from_team_id": t2, "to_team_id": t1},
            ],
        },
    )
    assert trade.status_code == 200
    trade_id = trade.json()["trade_id"]

    accepted = expansion_client.post(
        f"/api/cfb/leagues/{league_id}/trades/{trade_id}/accept",
        json={"accepting_team_id": t2},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "completed"

    r1 = expansion_client.get(f"/api/cfb/leagues/{league_id}/teams/{t1}/roster").json()["roster"]
    assert any(r["player_id"] == p2 for r in r1)


def test_live_sse_returns_update(expansion_client, expansion_db):
    league_id = _create_league(expansion_client)
    with expansion_client.stream("GET", f"/api/cfb/leagues/{league_id}/weeks/1/live") as resp:
        assert resp.status_code == 200
        chunks = list(resp.iter_lines())
    assert any("teams" in line for line in chunks if line.startswith("data:"))


def test_playoff_seed(expansion_client):
    league_id = _create_league(expansion_client, num_teams=4)
    _create_teams(expansion_client, league_id, ["S1", "S2", "S3", "S4"])
    seed = expansion_client.post(f"/api/cfb/leagues/{league_id}/playoffs/seed")
    assert seed.status_code == 200
    bracket = seed.json()
    assert len(bracket["matchups"]) >= 1
    assert all(m.get("is_playoff") == 1 for m in bracket["matchups"])


def test_draft_help_returns_recommendations(expansion_client, expansion_db):
    _, pids = expansion_db
    league_id = _create_league(expansion_client)
    team_id = _create_teams(expansion_client, league_id, ["Help Team"])[0]
    expansion_client.post(
        f"/api/cfb/leagues/{league_id}/teams/{team_id}/roster",
        json={"add": [pids["Jalen Milroe"]], "drop": []},
    )
    help_resp = expansion_client.post(
        f"/api/cfb/leagues/{league_id}/draft-help",
        json={"team_id": team_id, "num_players": 10},
    )
    assert help_resp.status_code == 200
    recs = help_resp.json()["recommendations"]
    assert len(recs) <= 10
    assert all("reasons" in r for r in recs)
