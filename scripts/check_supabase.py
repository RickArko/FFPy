"""Sanity-check the Supabase config in .env before starting the auth-enabled web app.

Usage:
    uv run python scripts/check_supabase.py [--token <bearer-token>]

Without --token: validates URL is reachable and the browser key is accepted on
/auth/v1/health and /auth/v1/settings.

With --token: additionally calls /auth/v1/user with the supplied bearer token
and (if SUPABASE_JWT_SECRET is set) verifies the token signature locally.
"""

from __future__ import annotations

import argparse
import os
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

    raw_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    url = Config.SUPABASE_URL.rstrip("/")
    browser_key = Config.SUPABASE_BROWSER_KEY
    secret = Config.SUPABASE_JWT_SECRET

    print(f"SUPABASE_URL             : {url or '(unset)'}")
    print(f"SUPABASE_PUBLISHABLE_KEY : {'set' if Config.SUPABASE_PUBLISHABLE_KEY else '(unset)'}")
    print(f"SUPABASE_ANON_KEY        : {'set as legacy fallback' if Config.SUPABASE_ANON_KEY else '(unset)'}")
    print(f"Active browser key       : {(browser_key[:18] + '...') if browser_key else '(unset)'}")
    print(f"SUPABASE_JWT_SECRET      : {'set' if secret else '(unset — backend will use JWKS)'}")
    print(f"WEB_AUTH_ENABLED         : {Config.WEB_AUTH_ENABLED}")
    print(f"SUPABASE_FETCH_USER_ON_VERIFY: {Config.SUPABASE_FETCH_USER_ON_VERIFY}")
    print()
    if raw_url and raw_url != url:
        print(f"{WARN}SUPABASE_URL was normalized from {raw_url} to {url}")
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

    if not browser_key:
        failures += not _check("Supabase browser key is set", False, "set SUPABASE_PUBLISHABLE_KEY")
        return 1
    _check("Supabase browser key is set", True)

    # Health endpoint requires the apikey header
    try:
        r = requests.get(f"{url}/auth/v1/health", headers={"apikey": browser_key}, timeout=5)
        _check(
            "GET /auth/v1/health (browser key)",
            r.status_code == 200,
            f"HTTP {r.status_code} {r.text[:120]}",
        )
        failures += r.status_code != 200
    except requests.RequestException as exc:
        failures += not _check("GET /auth/v1/health (browser key)", False, str(exc))

    # Settings endpoint exposes the project's auth providers — confirms browser key is accepted
    try:
        r = requests.get(f"{url}/auth/v1/settings", headers={"apikey": browser_key}, timeout=5)
        if r.status_code == 200:
            providers = list(r.json().get("external", {}).keys())
            _check(
                "GET /auth/v1/settings (browser key)",
                True,
                f"providers: {', '.join(providers) or 'email-only'}",
            )
        else:
            failures += not _check(
                "GET /auth/v1/settings (browser key)",
                False,
                f"HTTP {r.status_code} {r.text[:120]}",
            )
    except requests.RequestException as exc:
        failures += not _check("GET /auth/v1/settings (browser key)", False, str(exc))

    # JWKS endpoint used by the backend for RS256 token verification (no apikey required)
    try:
        r = requests.get(f"{url}/auth/v1/.well-known/jwks.json", timeout=5)
        if r.status_code == 200:
            key_count = len(r.json().get("keys", []))
            _check(
                "GET /auth/v1/.well-known/jwks.json",
                key_count > 0,
                f"{key_count} signing key(s)",
            )
            failures += key_count == 0
        else:
            failures += not _check(
                "GET /auth/v1/.well-known/jwks.json",
                False,
                f"HTTP {r.status_code} {r.text[:120]}",
            )
    except requests.RequestException as exc:
        failures += not _check("GET /auth/v1/.well-known/jwks.json", False, str(exc))

    if args.token:
        print()
        print("Token checks:")
        # Local verification (only meaningful if jwt_secret set or JWKS available)
        verifier = SupabaseTokenVerifier(
            supabase_url=url,
            anon_key=browser_key,
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
                headers={"Authorization": f"Bearer {args.token}", "apikey": browser_key},
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
