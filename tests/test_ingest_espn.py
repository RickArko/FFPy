"""Tests for ESPN ingest module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from ffpy.ingest.espn import fetch_espn_league


def _make_mock_response(status=200, data=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = data or {}
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} Error", response=resp)
    return resp


class TestFetchEspnLeague:
    @patch("ffpy.integrations.espn_league.requests.get")
    def test_public_league(self, mock_get):
        """Public league should work without cookies."""
        league_data = {
            "settings": {"name": "Public League", "playoffTeamCount": 4},
            "teams": [
                {
                    "id": 1,
                    "name": "Team 1",
                    "primaryOwner": "Alice",
                    "record": {
                        "overall": {"wins": 5, "losses": 2, "ties": 0, "pointsFor": 800, "pointsAgainst": 700}
                    },
                }
            ],
            "schedule": [
                {
                    "matchupPeriodId": 1,
                    "home": {"teamId": 1, "totalPoints": 110},
                    "away": {"teamId": 2, "totalPoints": 90},
                    "winner": "home",
                }
            ],
        }
        side_effects = []
        for _ in range(3):
            side_effects.append(_make_mock_response(200, league_data))
        for _ in range(17):
            side_effects.append(_make_mock_response(200, {"schedule": []}))

        mock_get.side_effect = side_effects

        data = fetch_espn_league("123456", season=2024, interactive=False)

        assert data["league"]["provider"] == "espn"
        assert data["league"]["league_id"] == "espn:123456"
        assert data["league"]["name"] == "Public League"
        assert len(data["teams"]) == 1
        assert data["teams"][0]["name"] == "Team 1"

    @patch("ffpy.integrations.espn_league.requests.get")
    def test_private_league_with_cookies(self, mock_get):
        """Private league should use cookies when provided."""
        league_data = {
            "settings": {"name": "Private League", "playoffTeamCount": 4},
            "teams": [],
            "schedule": [],
        }
        side_effects = [
            _make_mock_response(401),  # public get_league_info fails immediately
        ]
        # Private attempt with cookies: mSettings, mTeam, mRoster
        for _ in range(3):
            side_effects.append(_make_mock_response(200, league_data))
        for _ in range(17):
            side_effects.append(_make_mock_response(200, {"schedule": []}))

        mock_get.side_effect = side_effects

        data = fetch_espn_league(
            "123456",
            season=2024,
            swid="{TEST-SWID}",
            espn_s2="TEST-S2",
            interactive=False,
        )

        assert data["league"]["provider"] == "espn"
        assert data["league"]["name"] == "Private League"

        # Verify the first request after public failure had cookies
        calls = mock_get.call_args_list
        auth_calls = [c for c in calls if "cookies" in c.kwargs and c.kwargs["cookies"]]
        assert len(auth_calls) > 0
        assert auth_calls[0].kwargs["cookies"]["swid"] == "{TEST-SWID}"

    @patch("ffpy.integrations.espn_league.requests.get")
    def test_private_league_no_cookies_raises(self, mock_get):
        """Private league with no cookies should raise."""
        mock_get.side_effect = [_make_mock_response(401)]

        with pytest.raises(RuntimeError, match="private"):
            fetch_espn_league("123456", season=2024, interactive=False)

    @patch("ffpy.integrations.espn_league.requests.get")
    def test_non_auth_http_error_is_reraised(self, mock_get):
        """Non-auth failures should not be treated as a private league."""
        mock_get.side_effect = [_make_mock_response(500)]

        with pytest.raises(requests.HTTPError, match="500"):
            fetch_espn_league("123456", season=2024, interactive=False)

    @patch("ffpy.integrations.espn_league.requests.get")
    def test_normalized_data_shape(self, mock_get):
        """Verify the output dict matches DB schema expectations."""
        league_data = {
            "settings": {"name": "Test League", "playoffTeamCount": 6},
            "teams": [
                {
                    "id": 1,
                    "name": "Team A",
                    "abbrev": "TA",
                    "primaryOwner": "Alice",
                    "record": {
                        "overall": {"wins": 5, "losses": 2, "ties": 0, "pointsFor": 800, "pointsAgainst": 700}
                    },
                }
            ],
            "schedule": [],
        }
        side_effects = []
        for _ in range(3):
            side_effects.append(_make_mock_response(200, league_data))
        for _ in range(17):
            side_effects.append(_make_mock_response(200, {"schedule": []}))

        mock_get.side_effect = side_effects

        data = fetch_espn_league("123456", season=2024, interactive=False)

        league = data["league"]
        assert league["league_id"] == "espn:123456"
        assert league["provider"] == "espn"
        assert league["season"] == 2024
        assert isinstance(league["scoring_type"], str)

        for team in data["teams"]:
            assert "team_id" in team
            assert "name" in team
            assert "wins" in team
            assert "losses" in team
            assert "points_for" in team
            assert "roster" in team

        for m in data["matchups"]:
            assert "week" in m
            assert "home_team_id" in m
            assert "away_team_id" in m
            assert "is_playoff" in m

    @patch("ffpy.integrations.espn_league.requests.get")
    def test_matchups_stop_on_empty(self, mock_get):
        """Matchup fetching should stop when ESPN returns empty/future weeks."""
        league_data = {
            "settings": {"name": "Test"},
            "teams": [{"id": 1, "record": {"overall": {}}}],
            "schedule": [],
        }
        responses = []
        # 3 calls for league info, teams, rosters
        for _ in range(3):
            responses.append(_make_mock_response(200, league_data))
        # Only week 1 has data
        responses.append(
            _make_mock_response(
                200,
                {
                    "schedule": [
                        {
                            "matchupPeriodId": 1,
                            "home": {"teamId": 1, "totalPoints": 100},
                            "away": {"teamId": 2, "totalPoints": 90},
                        }
                    ]
                },
            )
        )
        # Week 2 is empty → stops
        responses.append(_make_mock_response(200, {"schedule": []}))

        mock_get.side_effect = responses

        data = fetch_espn_league("123456", season=2024, interactive=False)
        assert len(data["matchups"]) == 1
        assert data["matchups"][0]["week"] == 1
