"""Output formatters: table, JSON, CSV, and optional DB persistence."""

from __future__ import annotations

import csv
import json
import logging
import sys
from typing import Any, Dict, List, Optional, TextIO

from ffpy.database import FFPyDatabase

logger = logging.getLogger(__name__)


def write_json(data: Any, file: TextIO = sys.stdout) -> None:
    json.dump(data, file, indent=2, default=str)
    file.write("\n")


def write_csv(data: List[Dict[str, Any]], file: TextIO = sys.stdout) -> None:
    if not data:
        return
    writer = csv.DictWriter(file, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)


def write_table(data: List[Dict[str, Any]], file: TextIO = sys.stdout) -> None:
    """Simple aligned-column table output."""
    if not data:
        return
    headers = list(data[0].keys())
    rows = [[str(r.get(h, "")) for h in headers] for r in data]
    col_widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]

    sep = "  "
    header_line = sep.join(h.ljust(w) for h, w in zip(headers, col_widths))
    file.write(header_line + "\n")
    file.write("-" * len(header_line) + "\n")
    for row in rows:
        file.write(sep.join(cell.ljust(w) for cell, w in zip(row, col_widths)) + "\n")


def persist_to_db(data: dict, user_id: str = "cli", db_path: Optional[str] = None) -> str:
    """Store ingested league data in the FFPy SQLite database.

    Returns the league_id (prefixed string like ``espn:123456``).
    """
    db = FFPyDatabase(db_path=db_path)
    try:
        league_id = db.store_user_league(user_id, data)
        logger.info(
            "Stored league %s (%d teams, %d matchups)",
            league_id,
            len(data.get("teams", [])),
            len(data.get("matchups", [])),
        )
        return league_id
    finally:
        db.close()


def format_output(data: Any, fmt: str, file: TextIO = sys.stdout) -> None:
    """Dispatch to the correct formatter based on *fmt* (json|csv|table)."""
    if fmt == "json":
        write_json(data, file)
    elif fmt == "csv":
        if isinstance(data, dict):
            write_csv([data], file)
        elif isinstance(data, list):
            write_csv(data, file)
        else:
            write_json(data, file)
    else:
        if isinstance(data, dict):
            write_table([data], file)
        elif isinstance(data, list):
            write_table(data, file)
        else:
            file.write(str(data) + "\n")
