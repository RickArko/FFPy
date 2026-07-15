"""Tests for the ffpy-ingest CLI argument parsing."""

from __future__ import annotations

from ffpy.ingest.cli import build_parser


class TestCliArgparse:
    def setup_method(self):
        self.parser = build_parser()

    def test_espn_defaults(self):
        args = self.parser.parse_args(["espn", "123456"])
        assert args.command == "espn"
        assert args.league_id == "123456"
        assert args.season == 2025
        assert args.format == "table"
        assert args.swid is None
        assert args.s2 is None

    def test_espn_custom_season(self):
        args = self.parser.parse_args(["espn", "123456", "--season", "2024"])
        assert args.season == 2024

    def test_espn_with_cookies(self):
        args = self.parser.parse_args(["espn", "123456", "--swid", "{swid}", "--s2", "s2val"])
        assert args.swid == "{swid}"
        assert args.s2 == "s2val"

    def test_yahoo_defaults(self):
        args = self.parser.parse_args(["yahoo", "389.l.12345"])
        assert args.command == "yahoo"
        assert args.league_id == "389.l.12345"
        assert args.season == 2025

    def test_sleeper_defaults(self):
        args = self.parser.parse_args(["sleeper", "league123"])
        assert args.command == "sleeper"
        assert args.league_id == "league123"
        assert args.season == 2025

    def test_json_flag(self):
        args = self.parser.parse_args(["--json", "espn", "123456"])
        assert args.format == "json"

    def test_csv_flag(self):
        args = self.parser.parse_args(["--csv", "yahoo", "389.l.12345"])
        assert args.format == "csv"

    def test_yahoo_auth(self):
        args = self.parser.parse_args(["yahoo-auth"])
        assert args.command == "yahoo-auth"

    def test_yahoo_token(self):
        args = self.parser.parse_args(["yahoo-token", "--code", "abc123"])
        assert args.command == "yahoo-token"
        assert args.code == "abc123"

    def test_leagues_list(self):
        args = self.parser.parse_args(["leagues-list"])
        assert args.command == "leagues-list"

    def test_leagues_info(self):
        args = self.parser.parse_args(["leagues-info", "espn:123456"])
        assert args.command == "leagues-info"
        assert args.id == "espn:123456"

    def test_roster(self):
        args = self.parser.parse_args(["roster", "espn:123456", "espn:123456:1"])
        assert args.command == "roster"
        assert args.league_id == "espn:123456"
        assert args.team_id == "espn:123456:1"

    def test_matchups(self):
        args = self.parser.parse_args(["matchups", "espn:123456", "3"])
        assert args.command == "matchups"
        assert args.league_id == "espn:123456"
        assert args.week == 3

    def test_db_flag(self):
        args = self.parser.parse_args(["--db", "/tmp/test.db", "sleeper", "league1"])
        assert args.db == "/tmp/test.db"
