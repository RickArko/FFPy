"""S5 / F5 contracts: no CFB on new DBs, Streamlit isolated, projection re-export."""

from __future__ import annotations

import sqlite3
import sys


def test_new_database_has_no_cfb_tables(tmp_path):
    from ffpy.database import FFPyDatabase

    db = FFPyDatabase(str(tmp_path / "new.db"))
    names = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'cfb_%'"
        )
    }
    db.close()
    assert names == set()


def test_existing_cfb_database_still_opens(tmp_path):
    from pathlib import Path

    from ffpy.database import FFPyDatabase

    path = tmp_path / "legacy.db"
    schema = Path(__file__).resolve().parents[1] / "src" / "ffpy" / "migrations" / "015_cfb_schema.sql"
    with sqlite3.connect(path) as conn:
        conn.executescript(schema.read_text(encoding="utf-8"))
    db = FFPyDatabase(str(path))
    row = db.conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'cfb_games'").fetchone()
    db.close()
    assert row is not None


def test_import_database_does_not_import_streamlit():
    before = {name for name in sys.modules if name == "streamlit" or name.startswith("streamlit.")}
    if "ffpy.database" in sys.modules:
        del sys.modules["ffpy.database"]
    import ffpy.database  # noqa: F401

    after = {name for name in sys.modules if name == "streamlit" or name.startswith("streamlit.")}
    assert after == before


def test_projection_reexport_prefers_nfl_data():
    from nfl_data.projections.model import EnhancedProjectionModel as NflModel

    from ffpy.projections import EnhancedProjectionModel

    assert EnhancedProjectionModel is NflModel
