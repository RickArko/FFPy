"""CBS client parsing — fixtures only, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ffpy.integrations.cbs_league import (
    CBSAuthError,
    _parse_response,
    parse_cbs_league_id,
    redact_cbs_secret,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cbs"


class _Response:
    def __init__(self, status: int, body: str):
        self.status_code = status
        self.text = body

    def json(self) -> dict:
        return json.loads(self.text)


def test_invalid_token_is_auth_error():
    observed = json.loads((FIXTURES / "errors.json").read_text(encoding="utf-8"))["invalid_token"]
    with pytest.raises(CBSAuthError):
        _parse_response(_Response(observed["status"], observed["body"]))


def test_missing_league_id_is_not_auth_error():
    from ffpy.integrations.cbs_league import CBSAPIError

    observed = json.loads((FIXTURES / "errors.json").read_text(encoding="utf-8"))["missing_league_id"]
    with pytest.raises(CBSAPIError):
        _parse_response(_Response(observed["status"], observed["body"]))


def test_parse_cbs_league_id_from_url_and_bare_id():
    assert parse_cbs_league_id("https://dadleague.football.cbssports.com/teams") == "dadleague"
    assert parse_cbs_league_id("https://www.cbssports.com/fantasy?league_id=abc-12") == "abc-12"
    assert parse_cbs_league_id("12345") == "12345"
    with pytest.raises(ValueError):
        parse_cbs_league_id("https://example.com/not-cbs")


def test_redact_cbs_secret():
    raw = "https://api.cbssports.com/fantasy/league/details?access_token=super-secret&league_id=1"
    assert "super-secret" not in redact_cbs_secret(raw)
    assert "access_token=REDACTED" in redact_cbs_secret(raw)
