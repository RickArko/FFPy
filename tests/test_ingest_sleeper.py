"""Tests for Sleeper ingest module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from ffpy.ingest.sleeper import fetch_sleeper_league


def _mock_json(data):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.json.return_value = data
    return resp


class TestFetchSleeperLeague:
    @patch("ffpy.integrations.sleeper.requests.get")
    @patch("ffpy.ingest.sleeper._load_sleeper_players")
    def test_basic_league(self, mock_players, mock_get):
        """Verify normal Sleeper league import."""
        mock_players.return_value = {
            "1234": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC"},
            "5678": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
        }

        mock_get.side_effect = [
            _mock_json(
                {"name": "Test League", "season": 2024, "total_rosters": 2, "settings": {"playoff_teams": 4}}
            ),
            _mock_json(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "user_a",
                        "players": ["1234", "5678"],
                        "settings": {"wins": 5, "losses": 2, "ties": 0, "fpts": 800, "fpts_against": 700},
                    },
                    {
                        "roster_id": 2,
                        "owner_id": "user_b",
                        "players": [],
                        "settings": {"wins": 3, "losses": 4, "ties": 0, "fpts": 650, "fpts_against": 750},
                    },
                ]
            ),
            _mock_json(
                [
                    {"user_id": "user_a", "display_name": "Alice", "metadata": {"team_name": "A-Team"}},
                    {"user_id": "user_b", "display_name": "Bob", "metadata": {}},
                ]
            ),
            _mock_json(
                [
                    {"matchup_id": 1, "roster_id": 1, "points": 110.5},
                    {"matchup_id": 1, "roster_id": 2, "points": 98.3},
                ]
            ),
        ]

        data = fetch_sleeper_league("test_league", season=2024)

        assert data["league"]["provider"] == "sleeper"
        assert data["league"]["name"] == "Test League"
        assert data["league"]["season"] == 2024
        assert data["league"]["num_teams"] == 2

        assert len(data["teams"]) == 2
        team_a = data["teams"][0]
        assert team_a["name"] == "A-Team"
        assert team_a["owner"] == "Alice"
        assert team_a["wins"] == 5
        assert len(team_a["roster"]) == 2
        assert team_a["roster"][0]["player"] == "Patrick Mahomes"

        assert len(data["matchups"]) == 1
        assert data["matchups"][0]["home_score"] == 110.5
        assert data["matchups"][0]["away_score"] == 98.3

    @patch("ffpy.integrations.sleeper.requests.get")
    @patch("ffpy.ingest.sleeper._load_sleeper_players")
    def test_empty_roster_slot_skipped(self, mock_players, mock_get):
        """Roster slots with no owner and no players should be skipped."""
        mock_players.return_value = {}

        mock_get.side_effect = [
            _mock_json({"name": "Test League", "season": 2024, "total_rosters": 3, "settings": {}}),
            _mock_json(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "user_a",
                        "players": ["1"],
                        "settings": {"wins": 1, "losses": 0, "ties": 0, "fpts": 100, "fpts_against": 50},
                    },
                    {
                        "roster_id": 2,
                        "owner_id": "",
                        "players": [],
                        "settings": {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_against": 0},
                    },
                ]
            ),
            _mock_json([{"user_id": "user_a", "display_name": "Alice"}]),
            _mock_json([]),
        ]

        data = fetch_sleeper_league("test_league", season=2024)
        assert len(data["teams"]) == 1
        assert len(data["matchups"]) == 0

    @patch("ffpy.integrations.sleeper.requests.get")
    @patch("ffpy.ingest.sleeper._load_sleeper_players")
    def test_teams_sorted_by_record(self, mock_players, mock_get):
        """Teams should be sorted by wins descending, then points_for."""
        mock_players.return_value = {}

        mock_get.side_effect = [
            _mock_json({"name": "Test", "season": 2024, "total_rosters": 3, "settings": {}}),
            _mock_json(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "a",
                        "players": ["1"],
                        "settings": {"wins": 5, "losses": 2, "ties": 0, "fpts": 800, "fpts_against": 700},
                    },
                    {
                        "roster_id": 2,
                        "owner_id": "b",
                        "players": ["2"],
                        "settings": {"wins": 5, "losses": 2, "ties": 0, "fpts": 750, "fpts_against": 720},
                    },
                    {
                        "roster_id": 3,
                        "owner_id": "c",
                        "players": ["3"],
                        "settings": {"wins": 3, "losses": 4, "ties": 0, "fpts": 650, "fpts_against": 750},
                    },
                ]
            ),
            _mock_json(
                [
                    {"user_id": "a", "display_name": "Alice"},
                    {"user_id": "b", "display_name": "Bob"},
                    {"user_id": "c", "display_name": "Charlie"},
                ]
            ),
            _mock_json([]),
        ]

        data = fetch_sleeper_league("test_league", season=2024)
        assert len(data["teams"]) == 3
        assert data["teams"][0]["name"] == "Alice"
        assert data["teams"][1]["name"] == "Bob"
        assert data["teams"][2]["name"] == "Charlie"
