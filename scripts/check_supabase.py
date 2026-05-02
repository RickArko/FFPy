"""Sanity-check the Supabase config in .env before starting the auth-enabled web app.

Usage:
    uv run python scripts/check_supabase.py [--token <bearer-token>]

Without --token: validates URL is reachable and the anon key is accepted on
/auth/v1/health and /auth/v1/settings.

With --token: additionally calls /auth/v1/user with the supplied bearer token
and (if SUPABASE_JWT_SECRET is set) verifies the token signature locally.
"""

from __future__ import annotations

import argparse
import sys

import requests

from ffpy.auth import SupabaseTokenVerifier, TokenVerificationError
from ffpy.config import Config

OK = "[OK]   "
WARN = "[WARN] "
FAIL = "[FAIL] "


def _check(label: str, ok: bool, detail: str = "") -> bool:
    prefix = OK if ok else FAIL
    print(f"{prefix}{label}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Bearer token to test against /auth/v1/user")
    args = parser.parse_args()

    url = Config.SUPABASE_URL.rstrip("/")
    anon = Config.SUPABASE_ANON_KEY
    secret = Config.SUPABASE_JWT_SECRET

    print(f"SUPABASE_URL             : {url or '(unset)'}")
    print(f"SUPABASE_ANON_KEY        : {(anon[:18] + '...') if anon else '(unset)'}")
    print(f"SUPABASE_JWT_SECRET      : {'set' if secret else '(unset — backend will use JWKS)'}")
    print(f"WEB_AUTH_ENABLED         : {Config.WEB_AUTH_ENABLED}")
    print(f"SUPABASE_FETCH_USER_ON_VERIFY: {Config.SUPABASE_FETCH_USER_ON_VERIFY}")
    print()

    failures = 0

    if not url:
        failures += not _check("SUPABASE_URL is set", False, "blank")
        return 1
    if "/dashboard/" in url or "supabase.com" in url:
        failures += not _check(
            "SUPABASE_URL looks like an API endpoint",
            False,
            "expected https://<project-ref>.supabase.co, got dashboard URL",
        )
        return 1
    _check("SUPABASE_URL looks like an API endpoint", True)

    if not anon:
        failures += not _check("SUPABASE_ANON_KEY is set", False, "blank")
        return 1
    _check("SUPABASE_ANON_KEY is set", True)

    # Health endpoint requires the apikey header
    try:
        r = requests.get(f"{url}/auth/v1/health", headers={"apikey": anon}, timeout=5)
        _check(
            "GET /auth/v1/health (anon key)",
            r.status_code == 200,
            f"HTTP {r.status_code} {r.text[:120]}",
        )
        failures += r.status_code != 200
    except requests.RequestException as exc:
        failures += not _check("GET /auth/v1/health (anon key)", False, str(exc))

    # Settings endpoint exposes the project's auth providers — confirms anon key is accepted
    try:
        r = requests.get(f"{url}/auth/v1/settings", headers={"apikey": anon}, timeout=5)
        if r.status_code == 200:
            providers = list(r.json().get("external", {}).keys())
            _check(
                "GET /auth/v1/settings (anon key)",
                True,
                f"providers: {', '.join(providers) or 'email-only'}",
            )
        else:
            failures += not _check(
                "GET /auth/v1/settings (anon key)",
                False,
                f"HTTP {r.status_code} {r.text[:120]}",
            )
    except requests.RequestException as exc:
        failures += not _check("GET /auth/v1/settings (anon key)", False, str(exc))

    if args.token:
        print()
        print("Token checks:")
        # Local verification (only meaningful if jwt_secret set or JWKS available)
        verifier = SupabaseTokenVerifier(
            supabase_url=url,
            anon_key=anon,
            jwt_secret=secret,
            audience=Config.SUPABASE_JWT_AUDIENCE,
            fetch_user_on_verify=False,  # split into its own check below
        )
        try:
            user = verifier.verify_access_token(args.token)
            _check(
                "Local signature verify",
                True,
                f"sub={user.user_id} email={user.email} role={user.role}",
            )
        except TokenVerificationError as exc:
            failures += not _check("Local signature verify", False, str(exc))

        # Userinfo round-trip
        try:
            r = requests.get(
                f"{url}/auth/v1/user",
                headers={"Authorization": f"Bearer {args.token}", "apikey": anon},
                timeout=5,
            )
            if r.status_code == 200:
                payload = r.json()
                _check(
                    "GET /auth/v1/user (bearer token)",
                    True,
                    f"id={payload.get('id')} email={payload.get('email')}",
                )
            else:
                failures += not _check(
                    "GET /auth/v1/user (bearer token)",
                    False,
                    f"HTTP {r.status_code} {r.text[:160]}",
                )
        except requests.RequestException as exc:
            failures += not _check("GET /auth/v1/user (bearer token)", False, str(exc))

    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    if not Config.WEB_AUTH_ENABLED:
        print(f"{WARN}WEB_AUTH_ENABLED=false — set to true to actually use auth in the app.")
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
