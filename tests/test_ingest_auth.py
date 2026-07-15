"""Tests for ingest auth helpers."""

from __future__ import annotations

import json

from ffpy.ingest import auth


class TestYahooToken:
    def test_save_and_load(self, tmp_path):
        auth.TOKEN_DIR = tmp_path
        auth.TOKEN_FILE = tmp_path / "yahoo_token.json"

        token = {"access_token": "test", "expires_at": 9999999999}
        auth.save_yahoo_token(token)

        loaded = auth.load_yahoo_token()
        assert loaded["access_token"] == "test"

    def test_load_missing(self, tmp_path):
        auth.TOKEN_DIR = tmp_path
        auth.TOKEN_FILE = tmp_path / "yahoo_token.json"

        assert auth.load_yahoo_token() is None

    def test_load_corrupt(self, tmp_path):
        auth.TOKEN_DIR = tmp_path
        auth.TOKEN_FILE = tmp_path / "yahoo_token.json"
        auth.TOKEN_FILE.write_text("{bad json")

        assert auth.load_yahoo_token() is None

    def test_expired_token(self, tmp_path):
        auth.TOKEN_DIR = tmp_path
        auth.TOKEN_FILE = tmp_path / "yahoo_token.json"
        auth.save_yahoo_token({"access_token": "old", "expires_at": 0})

        loaded = auth.load_yahoo_token()
        assert loaded is not None  # Still returned; caller should refresh

    def test_delete(self, tmp_path):
        auth.TOKEN_DIR = tmp_path
        auth.TOKEN_FILE = tmp_path / "yahoo_token.json"
        auth.save_yahoo_token({"access_token": "test"})
        auth.delete_yahoo_token()
        assert not auth.TOKEN_FILE.exists()


class TestEspnCookies:
    def test_env_vars_take_priority(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ESPN_SWID", "{ENV-SWID}")
        monkeypatch.setenv("ESPN_S2", "ENV-S2")

        auth.COOKIE_FILE = tmp_path / "espn_cookies.json"
        auth.COOKIE_FILE.write_text(json.dumps({"swid": "{FILE-SWID}", "espn_s2": "FILE-S2"}))

        swid, s2 = auth.load_espn_cookies()
        assert swid == "{ENV-SWID}"
        assert s2 == "ENV-S2"

    def test_fallback_to_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ESPN_SWID", raising=False)
        monkeypatch.delenv("ESPN_S2", raising=False)

        auth.COOKIE_FILE = tmp_path / "espn_cookies.json"
        auth.COOKIE_FILE.write_text(json.dumps({"swid": "{FILE-SWID}", "espn_s2": "FILE-S2"}))

        swid, s2 = auth.load_espn_cookies()
        assert swid == "{FILE-SWID}"
        assert s2 == "FILE-S2"

    def test_save_and_delete(self, tmp_path):
        auth.COOKIE_FILE = tmp_path / "espn_cookies.json"

        auth.save_espn_cookies("{SWID}", "S2VAL")
        assert auth.COOKIE_FILE.exists()

        data = json.loads(auth.COOKIE_FILE.read_text())
        assert data["swid"] == "{SWID}"
        assert data["espn_s2"] == "S2VAL"

        auth.delete_espn_cookies()
        assert not auth.COOKIE_FILE.exists()
