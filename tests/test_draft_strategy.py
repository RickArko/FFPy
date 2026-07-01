"""Unit tests for the draft strategy engine."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ffpy.database import FFPyDatabase
from ffpy.draft_strategy import DraftStrategyConfig, DraftStrategyEngine, _resolve_roster


@pytest.fixture
def strategy_db(tmp_path: Path) -> FFPyDatabase:
  db = FFPyDatabase(db_path=str(tmp_path / "draft-strategy.db"))
  # Minimal ADP
  adp = pd.DataFrame(
    {
      "player_name": [
        "Star RB",
        "Value RB",
        "Star WR",
        "Stack WR",
        "Deep K",
        "Deep DST",
        "Rostered Guy",
      ],
      "position": ["RB", "RB", "WR", "WR", "K", "DST", "RB"],
      "platform": ["fantasypros"] * 7,
      "adp": [5.0, 55.0, 8.0, 60.0, 250.0, 255.0, 12.0],
      "adp_high": [3.0, 50.0, 6.0, 55.0, 240.0, 245.0, 10.0],
      "adp_low": [8.0, 60.0, 10.0, 65.0, 260.0, 265.0, 15.0],
    }
  )
  db.store_adp(adp, season=2026)

  # Players + weekly stats for correlation
  for name, pos, team, pid in [
    ("Josh Allen", "QB", "BUF", 1),
    ("Star RB", "RB", "KC", 2),
    ("Value RB", "RB", "DAL", 3),
    ("Star WR", "WR", "MIA", 4),
    ("Stack WR", "WR", "BUF", 5),
    ("Rostered Guy", "RB", "NYJ", 6),
  ]:
    db.conn.execute(
      "INSERT INTO players (player_id, name, nfl_id, team, position) VALUES (?, ?, ?, ?, ?)",
      (pid, name, f"gsis-{pid}", team, pos),
    )
    for week in range(1, 6):
      pts = 20.0 if pos == "QB" else 12.0 + pid
      if name == "Stack WR":
        pts = 14.0 + week
      db.conn.execute(
        """
        INSERT INTO actual_stats
          (player_id, season, week, actual_points, source)
        VALUES (?, 2025, ?, ?, 'test')
        """,
        (pid, week, pts),
      )
  db.conn.commit()
  yield db
  db.close()


def _league_and_teams():
  league = {
    "league_id": "test:1",
    "provider": "sleeper",
    "season": 2026,
    "league_name": "Test League",
  }
  my_roster = [
    {"player": "Josh Allen", "position": "QB", "team": "BUF"},
    {"player": "Rostered Guy", "position": "RB", "team": "NYJ"},
  ]
  teams = [
    {
      "team_id": "test:1:mine",
      "team_name": "Mine",
      "owner_name": "owner1",
      "roster_json": json.dumps(my_roster),
    },
    {
      "team_id": "test:1:other",
      "team_name": "Other",
      "owner_name": "owner2",
      "roster_json": json.dumps([{"player": "Star WR", "position": "WR", "team": "MIA"}]),
    },
  ]
  return league, teams


def test_resolve_roster_sleeper_ids():
  sleeper_players = {
    "99": {"full_name": "Test Player", "position": "RB", "team": "KC", "gsis_id": "x"},
  }
  roster = _resolve_roster(json.dumps(["99"]), "sleeper", sleeper_players)
  assert roster == [{"name": "Test Player", "position": "RB", "team": "KC"}]


def test_resolve_roster_dict_entries():
  roster = _resolve_roster(
    json.dumps([{"player": "Josh Allen", "position": "QB", "team": "BUF"}]),
    "espn",
    None,
  )
  assert roster[0]["name"] == "Josh Allen"


def test_generate_returns_top_rankings(strategy_db: FFPyDatabase):
  league, teams = _league_and_teams()
  engine = DraftStrategyEngine(
    strategy_db,
    DraftStrategyConfig(pick_slots=[1, 20], num_teams=10, corr_pool_size=20),
  )
  result = engine.generate(
    league=league,
    teams=teams,
    my_team_id="test:1:mine",
    num_players=5,
    sleeper_players={},
  )
  assert result["season"] == 2026
  assert len(result["rankings"]) == 5
  assert all("reasons" in r and r["reasons"] for r in result["rankings"])
  assert all(r["rank"] == i + 1 for i, r in enumerate(result["rankings"]))
  # Rostered player excluded
  names = {r["player"] for r in result["rankings"]}
  assert "Rostered Guy" not in names
  assert "Star WR" not in names  # on other team roster


def test_stack_wr_ranks_with_reason(strategy_db: FFPyDatabase):
  league, teams = _league_and_teams()
  engine = DraftStrategyEngine(strategy_db, DraftStrategyConfig(corr_pool_size=20))
  result = engine.generate(
    league=league,
    teams=teams,
    my_team_id="test:1:mine",
    num_players=10,
    sleeper_players={},
  )
  stack = next((r for r in result["rankings"] if r["player"] == "Stack WR"), None)
  assert stack is not None
  assert stack["stack"] is True
  assert any("stack" in reason.lower() for reason in stream["reasons"]) if (stream := stack) else False


def test_k_dst_not_top_over_skill(strategy_db: FFPyDatabase):
  league, teams = _league_and_teams()
  engine = DraftStrategyEngine(strategy_db, DraftStrategyConfig(corr_pool_size=20))
  result = engine.generate(
    league=league,
    teams=teams,
    my_team_id="test:1:mine",
    num_players=10,
    sleeper_players={},
  )
  top3_pos = [r["position"] for r in result["rankings"][:3]]
  assert "K" not in top3_pos
  assert "DST" not in top3_pos


def test_pick_recommendations(strategy_db: FFPyDatabase):
  league, teams = _league_and_teams()
  engine = DraftStrategyEngine(
    strategy_db,
    DraftStrategyConfig(pick_slots=[1, 20], num_teams=10, corr_pool_size=20),
  )
  result = engine.generate(
    league=league,
    teams=teams,
    my_team_id="test:1:mine",
    num_players=10,
    sleeper_players={},
  )
  assert len(result["picks"]) == 2
  assert result["picks"][0]["pick_slot"] == 1
  assert result["picks"][0]["player"]
  assert result["picks"][0]["reasons"]
