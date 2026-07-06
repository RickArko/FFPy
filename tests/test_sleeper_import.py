"""Unit tests for Sleeper league import enrichment."""

from __future__ import annotations

from unittest.mock import patch

from ffpy.integrations.sleeper import SleeperIntegration
from ffpy.league_api import _import_from_sleeper


def test_player_display_name_defense():
    player = {"position": "DEF", "first_name": "San Francisco", "last_name": "49ers", "team": "SF"}
    assert SleeperIntegration.player_display_name(player) == "San Francisco 49ers"


def test_enrich_roster_resolves_names():
    players_map = {
        "1234": {"full_name": "Josh Allen", "position": "QB", "team": "BUF"},
        "SF": {"position": "DEF", "first_name": "San Francisco", "last_name": "49ers", "team": "SF"},
    }
    roster = SleeperIntegration.enrich_roster(["1234", "SF"], players_map)
    assert roster[0]["player"] == "Josh Allen"
    assert roster[0]["position"] == "QB"
    assert roster[1]["player"] == "San Francisco 49ers"
    assert roster[1]["position"] == "DEF"


@patch("ffpy.draft_strategy.load_sleeper_players")
@patch("ffpy.league_api.SleeperIntegration.get_matchups")
@patch("ffpy.league_api.SleeperIntegration.get_league_users")
@patch("ffpy.league_api.SleeperIntegration.get_rosters")
@patch("ffpy.league_api.SleeperIntegration.get_league")
def test_import_from_sleeper_loads_player_db_and_resolves_names(
    mock_get_league,
    mock_get_rosters,
    mock_get_users,
    mock_get_matchups,
    mock_load_players,
):
    mock_get_league.return_value = {"name": "Test", "season": 2026, "total_rosters": 1}
    mock_get_rosters.return_value = [
        {"roster_id": 1, "owner_id": "owner_a", "players": ["99"], "settings": {}},
    ]
    mock_get_users.return_value = [{"user_id": "owner_a", "display_name": "alice", "metadata": {}}]
    mock_get_matchups.return_value = []
    mock_load_players.return_value = {
        "99": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC"},
    }

    data = _import_from_sleeper("league123", 2026)

    mock_load_players.assert_called_once()
    assert data["teams"][0]["roster"][0]["player"] == "Patrick Mahomes"
    assert data["teams"][0]["roster"][0]["position"] == "QB"
    assert data["teams"][0]["roster"][0]["team"] == "KC"


@patch("ffpy.draft_strategy.load_sleeper_players")
@patch("ffpy.league_api.SleeperIntegration.get_matchups")
@patch("ffpy.league_api.SleeperIntegration.get_league_users")
@patch("ffpy.league_api.SleeperIntegration.get_rosters")
@patch("ffpy.league_api.SleeperIntegration.get_league")
def test_import_from_sleeper_uses_league_users(
    mock_get_league,
    mock_get_rosters,
    mock_get_users,
    mock_get_matchups,
    mock_load_players,
):
    mock_get_league.return_value = {
        "name": "Test League",
        "season": 2026,
        "total_rosters": 2,
        "settings": {"playoff_teams": 4},
    }
    mock_get_rosters.return_value = [
        {
            "roster_id": 1,
            "owner_id": "owner_a",
            "players": ["99"],
            "settings": {"wins": 1, "losses": 0, "ties": 0, "fpts": 100, "fpts_against": 80},
        },
        {
            "roster_id": 2,
            "owner_id": "owner_b",
            "players": ["88"],
            "settings": {"wins": 0, "losses": 1, "ties": 0, "fpts": 80, "fpts_against": 100},
        },
    ]
    mock_get_users.return_value = [
        {
            "user_id": "owner_a",
            "display_name": "alice",
            "metadata": {"team_name": "Alice's Army"},
        },
        {
            "user_id": "owner_b",
            "display_name": "bob",
            "metadata": {"team_name": "Bob's Bunch"},
        },
    ]
    mock_get_matchups.return_value = []
    mock_load_players.return_value = {
        "99": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC"},
        "88": {"full_name": "Travis Kelce", "position": "TE", "team": "KC"},
    }

    data = _import_from_sleeper("league123", 2026)

    assert len(data["teams"]) == 2
    assert data["teams"][0]["name"] == "Alice's Army"
    assert data["teams"][0]["owner"] == "alice"
    assert data["teams"][0]["team_id"] == "sleeper:league123:1"
    assert data["teams"][0]["roster"][0]["player"] == "Patrick Mahomes"
    assert data["teams"][0]["roster"][0]["position"] == "QB"
    assert data["teams"][1]["name"] == "Bob's Bunch"


@patch("ffpy.draft_strategy.load_sleeper_players")
@patch("ffpy.league_api.SleeperIntegration.get_matchups")
@patch("ffpy.league_api.SleeperIntegration.get_league_users")
@patch("ffpy.league_api.SleeperIntegration.get_rosters")
@patch("ffpy.league_api.SleeperIntegration.get_league")
def test_import_from_sleeper_pairs_matchups(
    mock_get_league,
    mock_get_rosters,
    mock_get_users,
    mock_get_matchups,
    mock_load_players,
):
    mock_get_league.return_value = {"name": "Test", "season": 2026, "total_rosters": 2}
    mock_get_rosters.return_value = [
        {"roster_id": 1, "owner_id": "a", "players": [], "settings": {}},
        {"roster_id": 2, "owner_id": "b", "players": [], "settings": {}},
    ]
    mock_get_users.return_value = []
    mock_load_players.return_value = {}

    def matchups(league_id: str, week: int):
        if week > 1:
            return []
        return [
            {"roster_id": 1, "matchup_id": 1, "points": 110.0},
            {"roster_id": 2, "matchup_id": 1, "points": 95.5},
        ]

    mock_get_matchups.side_effect = matchups

    data = _import_from_sleeper("league123", 2026)
    assert len(data["matchups"]) == 1
    assert data["matchups"][0]["home_team_id"] == "sleeper:league123:1"
    assert data["matchups"][0]["away_team_id"] == "sleeper:league123:2"
    assert data["matchups"][0]["home_score"] == 110.0
    assert data["matchups"][0]["away_score"] == 95.5
