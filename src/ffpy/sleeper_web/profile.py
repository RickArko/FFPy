"""Supabase user ↔ Sleeper profile linking."""

from __future__ import annotations

from ffpy.database import FFPyDatabase
from ffpy.integrations.sleeper import SleeperIntegration


class ProfileLinkError(ValueError):
    """Raised when a Sleeper username cannot be linked."""


_PLACEHOLDER_USER_IDS = frozenset({"dev-user", "anon"})


class SleeperProfileService:
    """Validate and persist Sleeper profile links."""

    def __init__(self, db: FFPyDatabase):
        self.db = db

    def get_profile(self, user_id: str) -> dict | None:
        return self.db.get_sleeper_profile(user_id)

    def link_username(self, user_id: str, username: str) -> dict:
        if user_id in _PLACEHOLDER_USER_IDS:
            raise ProfileLinkError(
                "Sign in with Supabase (make run) before linking a Sleeper account. "
                "No-auth sessions cannot claim Sleeper profiles on the shared database."
            )
        username = username.strip()
        if not username:
            raise ProfileLinkError("Sleeper username is required")
        try:
            sleeper_user = SleeperIntegration.get_user(username)
        except Exception as exc:
            raise ProfileLinkError(f"Sleeper user '{username}' not found") from exc
        sleeper_user_id = str(sleeper_user.get("user_id") or "")
        if not sleeper_user_id:
            raise ProfileLinkError(f"Sleeper user '{username}' not found")
        existing = self.db.get_sleeper_profile_by_sleeper_user_id(sleeper_user_id)
        if existing and existing["user_id"] != user_id:
            raise ProfileLinkError("This Sleeper account is already linked to another user")
        return self.db.upsert_sleeper_profile(
            user_id,
            sleeper_user_id=sleeper_user_id,
            sleeper_username=username,
        )

    def unlink(self, user_id: str) -> None:
        self.db.delete_sleeper_profile(user_id)


__all__ = ["ProfileLinkError", "SleeperProfileService"]
