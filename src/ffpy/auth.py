"""Auth verification helpers for the hardened pick'em web app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

import jwt
import requests

from ffpy.config import Config


class TokenVerificationError(ValueError):
    """Raised when a bearer token cannot be verified or used."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """Server-side representation of the currently authenticated user."""

    user_id: str
    email: Optional[str]
    role: str
    email_confirmed: bool
    claims: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "email_confirmed": self.email_confirmed,
        }


class TokenVerifier(Protocol):
    """Token verification contract for auth-enabled API routes."""

    def verify_access_token(self, token: str) -> AuthenticatedUser: ...


class SupabaseTokenVerifier:
    """Verify Supabase-style user access tokens.

    Supports:
    - HS256 local/test tokens via `jwt_secret`
    - asymmetric Supabase tokens via the project's JWKS endpoint
    """

    def __init__(
        self,
        *,
        supabase_url: str = "",
        anon_key: str = "",
        jwt_secret: str = "",
        audience: str = "authenticated",
        issuer: Optional[str] = None,
        fetch_user_on_verify: bool = True,
        timeout_seconds: float = 5.0,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.anon_key = anon_key
        self.jwt_secret = jwt_secret
        self.audience = audience
        self.issuer = issuer or (
            f"{self.supabase_url}/auth/v1" if self.supabase_url else None
        )
        self.fetch_user_on_verify = fetch_user_on_verify
        self.timeout_seconds = timeout_seconds
        self.userinfo_url = (
            f"{self.supabase_url}/auth/v1/user" if self.supabase_url else None
        )
        self._jwks_client = (
            jwt.PyJWKClient(f"{self.supabase_url}/auth/v1/.well-known/jwks.json")
            if self.supabase_url and not self.jwt_secret
            else None
        )

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        if not token:
            raise TokenVerificationError("Missing bearer token")

        claims = self._decode_claims(token)

        if claims.get("role") != "authenticated":
            raise TokenVerificationError("Authenticated user token required")

        user_id = str(claims.get("sub") or "").strip()
        if not user_id:
            raise TokenVerificationError("Token missing subject claim")

        email_confirmed = self._email_confirmed_from_claims(claims)
        if email_confirmed is None and self.fetch_user_on_verify:
            email_confirmed = self._fetch_email_confirmation(token)

        return AuthenticatedUser(
            user_id=user_id,
            email=claims.get("email"),
            role=str(claims.get("role", "")),
            email_confirmed=bool(email_confirmed),
            claims=claims,
        )

    def _decode_claims(self, token: str) -> Dict[str, Any]:
        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["HS256"] if self.jwt_secret else None,
            "audience": self.audience,
            "options": {"require": ["exp", "iat", "sub"]},
        }
        if self.issuer:
            decode_kwargs["issuer"] = self.issuer

        try:
            if self.jwt_secret:
                return jwt.decode(token, self.jwt_secret, **decode_kwargs)

            if self._jwks_client is None:
                raise TokenVerificationError("Supabase verifier is not configured")

            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg", "RS256")
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            decode_kwargs["algorithms"] = [algorithm]
            return jwt.decode(token, signing_key.key, **decode_kwargs)
        except TokenVerificationError:
            raise
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(f"Invalid bearer token: {exc}") from exc

    def _email_confirmed_from_claims(self, claims: Dict[str, Any]) -> Optional[bool]:
        if "email_verified" in claims:
            return bool(claims["email_verified"])
        if claims.get("email_confirmed_at"):
            return True
        if claims.get("confirmed_at") and claims.get("email"):
            return True
        return None

    def _fetch_email_confirmation(self, token: str) -> bool:
        if not self.userinfo_url:
            return False

        headers = {"Authorization": f"Bearer {token}"}
        if self.anon_key:
            headers["apikey"] = self.anon_key

        try:
            response = requests.get(
                self.userinfo_url,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise TokenVerificationError("Could not verify current Supabase user") from exc

        if response.status_code != 200:
            raise TokenVerificationError("Could not load current Supabase user")

        payload = response.json()
        return bool(payload.get("email_confirmed_at") or payload.get("confirmed_at"))


def build_token_verifier_from_config() -> Optional[TokenVerifier]:
    """Create the default token verifier from environment configuration."""

    if not Config.WEB_AUTH_ENABLED:
        return None

    if not Config.SUPABASE_URL and not Config.SUPABASE_JWT_SECRET:
        return None

    return SupabaseTokenVerifier(
        supabase_url=Config.SUPABASE_URL,
        anon_key=Config.SUPABASE_ANON_KEY,
        jwt_secret=Config.SUPABASE_JWT_SECRET,
        audience=Config.SUPABASE_JWT_AUDIENCE,
        fetch_user_on_verify=Config.SUPABASE_FETCH_USER_ON_VERIFY,
    )
