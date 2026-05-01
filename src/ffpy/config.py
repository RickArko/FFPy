"""Configuration management for Fantasy Football app."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    """Application configuration loaded from environment variables."""

    # API Provider Selection
    API_PROVIDER = os.getenv("API_PROVIDER", "espn").lower()

    # API Keys
    SPORTSDATA_API_KEY = os.getenv("SPORTSDATA_API_KEY", "")
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

    # NFL Season Configuration
    NFL_SEASON = int(os.getenv("NFL_SEASON", "2024"))

    # Cache Settings
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default

    # Database Configuration
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path.home() / ".ffpy" / "ffpy.db"))
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")

    # Public web app configuration
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")
    WEB_AUTH_ENABLED = os.getenv("WEB_AUTH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    # Supabase auth configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
    SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    SUPABASE_FETCH_USER_ON_VERIFY = os.getenv("SUPABASE_FETCH_USER_ON_VERIFY", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # Anti-abuse configuration
    TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
    UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
    UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    ABUSE_HASH_SALT = os.getenv("ABUSE_HASH_SALT", "")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    MAX_BACKTESTS_PER_HOUR = int(os.getenv("MAX_BACKTESTS_PER_HOUR", "10"))
    MAX_COMPARES_PER_HOUR = int(os.getenv("MAX_COMPARES_PER_HOUR", "3"))
    MAX_DAILY_COST_UNITS = int(os.getenv("MAX_DAILY_COST_UNITS", "100"))

    @classmethod
    def get_api_provider(cls) -> str:
        """
        Get the configured API provider.

        Returns:
            API provider name ('espn' or 'sportsdata')
        """
        return cls.API_PROVIDER

    @classmethod
    def is_sportsdata_configured(cls) -> bool:
        """
        Check if SportsDataIO is properly configured.

        Returns:
            True if API key is set and valid
        """
        return cls.SPORTSDATA_API_KEY != "" and cls.SPORTSDATA_API_KEY != "your_sportsdata_api_key_here"

    @classmethod
    def get_active_api_key(cls) -> str:
        """
        Get the API key for the active provider.

        Returns:
            API key or empty string
        """
        if cls.API_PROVIDER == "sportsdata":
            return cls.SPORTSDATA_API_KEY
        elif cls.API_PROVIDER == "rapidapi":
            return cls.RAPIDAPI_KEY
        return ""

    @classmethod
    def debug_config(cls) -> dict:
        """
        Get configuration summary for debugging.

        Returns:
            Dictionary with config status
        """
        return {
            "api_provider": cls.API_PROVIDER,
            "sportsdata_configured": cls.is_sportsdata_configured(),
            "nfl_season": cls.NFL_SEASON,
            "cache_ttl": cls.CACHE_TTL,
            "web_auth_enabled": cls.WEB_AUTH_ENABLED,
        }
