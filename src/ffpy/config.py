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
        return (
            cls.SPORTSDATA_API_KEY != ""
            and cls.SPORTSDATA_API_KEY != "your_sportsdata_api_key_here"
        )

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
        }
