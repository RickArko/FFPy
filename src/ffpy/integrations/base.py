"""Base class for API integrations."""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional


class BaseAPIIntegration(ABC):
    """Abstract base class for fantasy football API integrations."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the API integration.

        Args:
            api_key: Optional API key for authenticated endpoints
        """
        self.api_key = api_key

    @abstractmethod
    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame:
        """
        Get fantasy football projections for a given week.

        Args:
            week: NFL week number (1-18)
            season: NFL season year

        Returns:
            DataFrame with player projections in standardized format
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the API is available and properly configured.

        Returns:
            True if API can be used, False otherwise
        """
        pass

    def normalize_projections(self, raw_data: dict) -> pd.DataFrame:
        """
        Normalize raw API data to standardized DataFrame format.

        Expected columns:
        - player: Player name
        - team: Team abbreviation
        - position: Position (QB, RB, WR, TE)
        - opponent: Opponent team abbreviation
        - projected_points: Projected fantasy points
        - week: NFL week number
        - Position-specific stats (passing_yards, rushing_yards, etc.)

        Args:
            raw_data: Raw data from API

        Returns:
            Normalized DataFrame
        """
        # Override in subclasses for API-specific transformation
        return pd.DataFrame(raw_data)
