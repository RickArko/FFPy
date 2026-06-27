"""Integration tests against real Sleeper public API."""

from __future__ import annotations

import pytest

from ffpy.integrations.sleeper import SleeperIntegration


class TestSleeperLeagueImport:
    """No auth needed — always runs against public Sleeper API."""

    @pytest.fixture(scope="class")
    def user_id(self):
        user = SleeperIntegration.get_user("sleeper")
        assert "user_id" in user
        return user["user_id"]

    @pytest.fixture(scope="class")
    def league_id(self, user_id: str):
        leagues = SleeperIntegration.get_user_leagues(user_id, 2022)
        assert isinstance(leagues, list)
        assert len(leagues) > 0, "User 'sleeper' has no leagues in 2022; cannot run league-specific tests"
        return leagues[0]["league_id"]

    def test_get_user(self):
        user = SleeperIntegration.get_user("sleeper")
        assert "user_id" in user

    def test_get_user_leagues(self, user_id: str):
        leagues = SleeperIntegration.get_user_leagues(user_id, 2022)
        assert isinstance(leagues, list)

    def test_get_league(self, league_id: str):
        league = SleeperIntegration.get_league(league_id)
        assert "name" in league
        assert "season" in league

    def test_get_rosters(self, league_id: str):
        rosters = SleeperIntegration.get_rosters(league_id)
        assert isinstance(rosters, list)

    def test_get_matchups(self, league_id: str):
        matchups = SleeperIntegration.get_matchups(league_id, 1)
        assert isinstance(matchups, list)

    def test_get_players(self):
        players = SleeperIntegration.get_players()
        assert isinstance(players, dict)
        assert len(players) > 1000
