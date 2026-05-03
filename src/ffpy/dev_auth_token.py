"""Local auth-token helper for the pick'em web app."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt

from ffpy.config import Config


def build_dev_token(
    *,
    secret: str,
    email: str = "demo@example.com",
    user_id: Optional[str] = None,
    audience: str = "authenticated",
    role: str = "authenticated",
    email_confirmed: bool = True,
    ttl_minutes: int = 60,
) -> str:
    """Create a local bearer token compatible with the Supabase verifier."""

    if not secret:
        raise ValueError("secret is required")
    if ttl_minutes <= 0:
        raise ValueError("ttl_minutes must be > 0")

    now = datetime.now(tz=timezone.utc)
    claims = {
        "sub": user_id or str(uuid4()),
        "email": email,
        "role": role,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    if email_confirmed:
        claims["email_confirmed_at"] = now.isoformat()

    return jwt.encode(claims, secret, algorithm="HS256")


def main() -> None:
    """CLI entry point for generating local auth tokens."""

    parser = argparse.ArgumentParser(
        description="Generate a local bearer token for the pick'em auth flow."
    )
    parser.add_argument(
        "--secret",
        default=Config.SUPABASE_JWT_SECRET,
        help="HS256 secret used by the local auth-enabled backend.",
    )
    parser.add_argument(
        "--email",
        default="demo@example.com",
        help="Email claim to embed in the token.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Optional user UUID. Defaults to a random UUID.",
    )
    parser.add_argument(
        "--audience",
        default=Config.SUPABASE_JWT_AUDIENCE,
        help="JWT audience claim.",
    )
    parser.add_argument(
        "--role",
        default="authenticated",
        help="Role claim expected by the backend.",
    )
    parser.add_argument(
        "--ttl-minutes",
        type=int,
        default=60,
        help="Token lifetime in minutes.",
    )
    confirmed_group = parser.add_mutually_exclusive_group()
    confirmed_group.add_argument(
        "--confirmed",
        action="store_true",
        help="Mark the token as email-verified.",
    )
    confirmed_group.add_argument(
        "--unconfirmed",
        action="store_true",
        help="Leave the token unverified for auth-gate testing.",
    )
    args = parser.parse_args()

    if not args.secret:
        raise SystemExit(
            "Set SUPABASE_JWT_SECRET in .env or pass --secret to mint a local token."
        )

    token = build_dev_token(
        secret=args.secret,
        email=args.email,
        user_id=args.user_id,
        audience=args.audience,
        role=args.role,
        email_confirmed=not args.unconfirmed,
        ttl_minutes=args.ttl_minutes,
    )
    print(token)


if __name__ == "__main__":
    main()
