"""Integration tests against real ESPN API. Skipped without env vars."""

from __future__ import annotations

import os

import pytest

from ffpy.integrations.espn_league import ESPNLeagueIntegration


class TestESPNLeagueImport:
    """Integration tests against real ESPN API. Skipped without env vars."""

    @pytest.fixture(scope="session")
    def espn_creds(self):
        swid = os.environ.get("ESPN_SWID")
        s2 = os.environ.get("ESPN_S2")
        if not swid or not s2:
            pytest.skip("Set ESPN_SWID and ESPN_S2 env vars")
        return swid, s2

    @pytest.fixture(scope="session")
    def league(self, espn_creds):
        league_id = int(os.environ.get("ESPN_LEAGUE_ID", "123456"))
        return ESPNLeagueIntegration(league_id, 2024, espn_creds[0], espn_creds[1])

    def test_league_info(self, league):
        info = league.get_league_info()
        assert "name" in info
        assert info["season"] == 2024

    def test_standings(self, league):
        standings = league.get_standings()
        assert not standings.empty
        assert all(c in standings.columns for c in ["name", "wins", "losses"])

    def test_all_rosters(self, league):
        rosters = league.get_league_rosters(week=1)
        assert len(rosters) > 0
        for team_id, roster_df in rosters.items():
            assert not roster_df.empty
            assert "player" in roster_df.columns

    def test_scoring_settings(self, league):
        settings = league.get_scoring_settings()
        assert "scoring_type" in settings
        assert settings["scoring_type"] in ("PPR", "Half-PPR", "Standard")
        assert "scoring_items" in settings
