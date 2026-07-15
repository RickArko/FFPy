"""Tests for ingest output formatters."""

from __future__ import annotations

import csv
import io
import json

from ffpy.ingest.output import format_output, persist_to_db, write_csv, write_json, write_table


class TestWriteJson:
    def test_dict_output(self):
        buf = io.StringIO()
        write_json({"a": 1, "b": 2}, buf)
        result = json.loads(buf.getvalue())
        assert result == {"a": 1, "b": 2}

    def test_list_output(self):
        buf = io.StringIO()
        write_json([{"x": 1}, {"x": 2}], buf)
        result = json.loads(buf.getvalue())
        assert len(result) == 2


class TestWriteCsv:
    def test_basic_csv(self):
        buf = io.StringIO()
        write_csv([{"name": "Alice", "score": "10"}, {"name": "Bob", "score": "20"}], buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"

    def test_empty_list(self):
        buf = io.StringIO()
        write_csv([], buf)
        assert buf.getvalue() == ""


class TestWriteTable:
    def test_basic_table(self):
        buf = io.StringIO()
        write_table([{"name": "Alice", "wins": "5"}, {"name": "Bob", "wins": "3"}], buf)
        output = buf.getvalue()
        assert "Alice" in output
        assert "name" in output

    def test_empty(self):
        buf = io.StringIO()
        write_table([], buf)
        assert buf.getvalue() == ""


class TestFormatOutput:
    def test_json_format(self):
        buf = io.StringIO()
        format_output({"key": "val"}, "json", buf)
        assert json.loads(buf.getvalue()) == {"key": "val"}

    def test_csv_format_list(self):
        buf = io.StringIO()
        format_output([{"a": "1"}], "csv", buf)
        assert "a" in buf.getvalue()

    def test_table_format_default(self):
        buf = io.StringIO()
        format_output([{"a": "1"}], "table", buf)
        assert "a" in buf.getvalue()


class TestPersistToDb:
    def test_store_and_retrieve(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        data = {
            "league": {
                "league_id": "sleeper:test123",
                "provider": "sleeper",
                "name": "Test League",
                "season": 2024,
                "scoring_type": "ppr",
                "roster_size": None,
                "num_teams": 2,
                "playoff_teams": None,
            },
            "teams": [
                {
                    "team_id": "sleeper:test123:1",
                    "name": "Team A",
                    "owner": "Alice",
                    "wins": 5,
                    "losses": 2,
                    "ties": 0,
                    "points_for": 800.0,
                    "points_against": 700.0,
                    "rank": 1,
                    "roster": [],
                },
                {
                    "team_id": "sleeper:test123:2",
                    "name": "Team B",
                    "owner": "Bob",
                    "wins": 3,
                    "losses": 4,
                    "ties": 0,
                    "points_for": 650.0,
                    "points_against": 750.0,
                    "rank": 2,
                    "roster": [],
                },
            ],
            "matchups": [
                {
                    "week": 1,
                    "home_team_id": "sleeper:test123:1",
                    "away_team_id": "sleeper:test123:2",
                    "home_score": 110.5,
                    "away_score": 98.3,
                    "is_playoff": 0,
                    "is_consolation": 0,
                }
            ],
        }
        league_id = persist_to_db(data, user_id="test_user", db_path=db_path)
        assert league_id == "sleeper:test123"

        from ffpy.database import FFPyDatabase

        db = FFPyDatabase(db_path=db_path)
        try:
            leagues = db.get_user_leagues("test_user")
            assert len(leagues) == 1
            assert leagues[0]["league_id"] == "sleeper:test123"

            teams = db.get_league_teams(league_id, "test_user")
            assert len(teams) == 2

            matchups = db.get_league_matchups(league_id, 1, "test_user")
            assert len(matchups) == 1
            assert matchups[0]["home_score"] == 110.5
        finally:
            db.close()
