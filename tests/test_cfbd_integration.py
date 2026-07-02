"""Tests for CFBD integration normalization."""

from __future__ import annotations

import json
from pathlib import Path

from ffpy.integrations.cfbd import (
    CFBDClient,
    normalize_cfbd_game_players,
    team_key_from_name,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cfbd"


def test_team_key_from_name():
    assert team_key_from_name("Alabama") == "alabama"
    assert team_key_from_name("Ohio State") == "ohio_state"


def test_normalize_cfbd_game_players_fixture():
    data = json.loads((FIXTURES / "game_players.json").read_text())
    df = normalize_cfbd_game_players(data, season=2024, week=1)
    assert not df.empty
    assert int(df["cfbd_athlete_id"].iloc[0]) == 4432577
    assert df["passing_yards"].sum() >= 280
    assert df["rushing_yards"].sum() >= 45


def test_normalize_cfbd_game_players_v2_fixture():
    """CFBD API now nests athletes under each stat type block."""
    data = json.loads((FIXTURES / "game_players_v2.json").read_text())
    df = normalize_cfbd_game_players(data, season=2024, week=1)
    assert not df.empty
    milroe = df[df["cfbd_athlete_id"] == 4432577]
    assert milroe["passing_yards"].sum() == 280
    assert milroe["passing_tds"].sum() == 3
    assert milroe["rushing_yards"].sum() == 45


def test_fetch_teams_from_fixture(monkeypatch):
    teams_data = json.loads((FIXTURES / "teams.json").read_text())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return teams_data

    def fake_get(self, path, params=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("requests.Session.get", fake_get)
    client = CFBDClient(api_key="test-key")
    df = client.fetch_teams(2024, conference="SEC")
    assert len(df) == 2
    assert set(df["conference"]) == {"SEC"}


def test_conference_filter_sec_big_ten_acc():
    """Ensure default conference tuple matches plan scope."""
    from ffpy.integrations.cfbd import DEFAULT_CONFERENCES

    assert "SEC" in DEFAULT_CONFERENCES
    assert "Big Ten" in DEFAULT_CONFERENCES
    assert "ACC" in DEFAULT_CONFERENCES
    assert len(DEFAULT_CONFERENCES) == 3
