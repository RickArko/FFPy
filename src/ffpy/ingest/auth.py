"""Auth helpers for ingest CLI: cookie files, token file I/O, env helpers."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".ffpy"
TOKEN_FILE = TOKEN_DIR / "yahoo_token.json"
COOKIE_FILE = TOKEN_DIR / "espn_cookies.json"


def _ensure_dir() -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Yahoo token file
# ---------------------------------------------------------------------------


def load_yahoo_token() -> Optional[dict]:
    """Load Yahoo OAuth token from ~/.ffpy/yahoo_token.json if valid."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt Yahoo token file: %s", TOKEN_FILE)
        return None

    expires_at = data.get("expires_at", 0)
    if time.time() >= expires_at:
        logger.info("Yahoo token expired — caller should refresh")
    return data


def save_yahoo_token(token: dict) -> None:
    """Persist Yahoo OAuth token to ~/.ffpy/yahoo_token.json."""
    _ensure_dir()
    TOKEN_FILE.write_text(json.dumps(token, indent=2))
    logger.info("Yahoo token saved to %s", TOKEN_FILE)


def delete_yahoo_token() -> None:
    """Remove stored Yahoo token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        logger.info("Yahoo token deleted")


# ---------------------------------------------------------------------------
# ESPN cookie file
# ---------------------------------------------------------------------------


def load_espn_cookies() -> tuple[str, str]:
    """Load ESPN cookies from ~/.ffpy/espn_cookies.json or env vars."""
    swid = os.getenv("ESPN_SWID", "")
    s2 = os.getenv("ESPN_S2", "")

    if not swid or not s2:
        if COOKIE_FILE.exists():
            try:
                data = json.loads(COOKIE_FILE.read_text())
                swid = data.get("swid", swid)
                s2 = data.get("espn_s2", s2)
            except (json.JSONDecodeError, OSError):
                pass

    return swid, s2


def save_espn_cookies(swid: str, espn_s2: str) -> None:
    """Persist ESPN cookies to ~/.ffpy/espn_cookies.json."""
    _ensure_dir()
    COOKIE_FILE.write_text(json.dumps({"swid": swid, "espn_s2": espn_s2}, indent=2))
    logger.info("ESPN cookies saved to %s", COOKIE_FILE)


def delete_espn_cookies() -> None:
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()
        logger.info("ESPN cookies deleted")
