"""Integration tests against real Yahoo API. Skipped without env vars."""

from __future__ import annotations

import os

import pytest

from ffpy.integrations.yahoo import YahooIntegration


class TestYahooLeagueImport:
    """Integration tests against real Yahoo API. Skipped without env vars."""

    @pytest.fixture(scope="session")
    def yahoo_creds(self):
        client_id = os.environ.get("YAHOO_CLIENT_ID")
        client_secret = os.environ.get("YAHOO_CLIENT_SECRET")
        access_token = os.environ.get("YAHOO_ACCESS_TOKEN")
        if not client_id or not client_secret or not access_token:
            pytest.skip("Set YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, and YAHOO_ACCESS_TOKEN env vars")
        return client_id, client_secret, access_token

    @pytest.fixture(scope="session")
    def integration(self, yahoo_creds):
        return YahooIntegration(
            client_id=yahoo_creds[0],
            client_secret=yahoo_creds[1],
            redirect_uri="http://localhost:8001",
        )

    def test_get_user_leagues(self, integration, yahoo_creds):
        leagues = integration.get_user_leagues(yahoo_creds[2])
        assert isinstance(leagues, list)

    def test_get_authorization_url(self, integration):
        url = integration.get_authorization_url()
        assert url.startswith("https://api.login.yahoo.com/oauth2/request_auth")
