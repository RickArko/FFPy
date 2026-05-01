"""Protected endpoint usage logging."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Optional, Protocol

from ffpy.config import Config


@dataclass(frozen=True)
class UsageEvent:
    """One protected API interaction."""

    route: str
    event_type: str
    success: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    denied_reason: Optional[str] = None
    strategy_names_json: str = "[]"
    cost_units: int = 0
    ip_hash: Optional[str] = None
    user_agent_hash: Optional[str] = None
    request_fingerprint: Optional[str] = None


class UsageEventLogger(Protocol):
    """Logging contract for protected endpoint activity."""

    def log_event(self, event: UsageEvent) -> None: ...


class NoopUsageEventLogger:
    """Default logger for environments that do not persist usage events yet."""

    def log_event(self, event: UsageEvent) -> None:
        return None


class InMemoryUsageEventLogger:
    """Test helper that keeps usage events in memory."""

    def __init__(self):
        self.events: list[UsageEvent] = []

    def log_event(self, event: UsageEvent) -> None:
        self.events.append(event)


class SQLiteUsageEventLogger:
    """Persist usage events in a small local SQLite table.

    This gives us immediate observability while the production Supabase-backed
    event writer is still being built.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def log_event(self, event: UsageEvent) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO web_usage_events (
                    route, event_type, success, user_id, email, denied_reason,
                    strategy_names_json, cost_units, ip_hash, user_agent_hash,
                    request_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.route,
                    event.event_type,
                    int(event.success),
                    event.user_id,
                    event.email,
                    event.denied_reason,
                    event.strategy_names_json,
                    event.cost_units,
                    event.ip_hash,
                    event.user_agent_hash,
                    event.request_fingerprint,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS web_usage_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    user_id TEXT,
                    email TEXT,
                    denied_reason TEXT,
                    strategy_names_json TEXT NOT NULL DEFAULT '[]',
                    cost_units INTEGER NOT NULL DEFAULT 0,
                    ip_hash TEXT,
                    user_agent_hash TEXT,
                    request_fingerprint TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.commit()
        finally:
            conn.close()


def hash_identifier(raw_value: Optional[str], *, salt: Optional[str] = None) -> Optional[str]:
    """Hash request identifiers so we can correlate abuse without storing raw PII."""

    if not raw_value:
        return None
    active_salt = salt if salt is not None else Config.ABUSE_HASH_SALT
    if not active_salt:
        return None
    return hashlib.sha256(f"{active_salt}:{raw_value}".encode("utf-8")).hexdigest()


def encode_strategy_names(strategy_names: list[str]) -> str:
    """Serialize strategy names into a compact logging payload."""

    return json.dumps(strategy_names, sort_keys=True)
