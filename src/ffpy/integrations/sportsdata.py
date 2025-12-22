"""SportsDataIO Fantasy Football API integration."""

import requests
import pandas as pd
from typing import Optional
from .base import BaseAPIIntegration


class SportsDataIntegration(BaseAPIIntegration):
    """SportsDataIO Fantasy Football API integration (paid, official)."""

    BASE_URL = "https://api.sportsdata.io/v3/nfl"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize SportsDataIO integration.

        Args:
            api_key: SportsDataIO API key (required)
        """
        super().__init__(api_key)

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return (
            self.api_key is not None
            and self.api_key != ""
            and self.api_key != "your_sportsdata_api_key_here"
        )

    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame:
        """
        Get fantasy projections from SportsDataIO.

        Args:
            week: NFL week number (1-18)
            season: NFL season year

        Returns:
            DataFrame with player projections
        """
        if not self.is_available():
            print("SportsDataIO API key not configured")
            return pd.DataFrame()

        try:
            # SportsDataIO has separate endpoints for each position
            all_projections = []

            # Get projections for each position
            for position in ["QB", "RB", "WR", "TE"]:
                position_data = self._get_position_projections(position, week, season)
                if not position_data.empty:
                    all_projections.append(position_data)

            if all_projections:
                return pd.concat(all_projections, ignore_index=True)
            return pd.DataFrame()

        except Exception as e:
            print(f"SportsDataIO API error: {e}")
            return pd.DataFrame()

    def _get_position_projections(
        self, position: str, week: int, season: int
    ) -> pd.DataFrame:
        """
        Get projections for a specific position.

        Args:
            position: Player position (QB, RB, WR, TE)
            week: NFL week number
            season: NFL season year

        Returns:
            DataFrame with position projections
        """
        # SportsDataIO endpoint format
        endpoint_map = {
            "QB": "scores/json/FantasyDefenseProjectionsByWeek",  # Changed to a generic one
            "RB": "scores/json/FantasyDefenseProjectionsByWeek",
            "WR": "scores/json/FantasyDefenseProjectionsByWeek",
            "TE": "scores/json/FantasyDefenseProjectionsByWeek",
        }

        # Actually, let's use the player projections endpoint
        url = f"{self.BASE_URL}/projections/json/PlayerGameProjectionStatsByWeek/{season}/{week}"

        headers = {"Ocp-Apim-Subscription-Key": self.api_key}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return self._parse_sportsdata_response(data, position, week)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print("SportsDataIO: Invalid API key")
            elif e.response.status_code == 403:
                print("SportsDataIO: API key not authorized for this endpoint")
            else:
                print(f"SportsDataIO HTTP error: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"SportsDataIO error for {position}: {e}")
            return pd.DataFrame()

    def _parse_sportsdata_response(
        self, data: list, position: str, week: int
    ) -> pd.DataFrame:
        """
        Parse SportsDataIO API response.

        Args:
            data: List of player projections from API
            position: Filter by position
            week: NFL week number

        Returns:
            Normalized DataFrame
        """
        players = []

        for player_data in data:
            try:
                # Filter by position
                player_position = player_data.get("Position", "")
                if player_position != position:
                    continue

                # Calculate fantasy points (PPR scoring)
                fantasy_points = player_data.get("FantasyPointsPPR", 0) or 0

                player_record = {
                    "player": player_data.get("Name", ""),
                    "team": player_data.get("Team", ""),
                    "position": player_position,
                    "opponent": player_data.get("Opponent", ""),
                    "projected_points": round(fantasy_points, 1),
                    "week": week,
                }

                # Add position-specific stats
                if position == "QB":
                    player_record.update(
                        {
                            "passing_yards": player_data.get("PassingYards", 0) or 0,
                            "passing_tds": player_data.get("PassingTouchdowns", 0) or 0,
                            "rushing_yards": player_data.get("RushingYards", 0) or 0,
                        }
                    )
                elif position in ["RB", "WR", "TE"]:
                    player_record.update(
                        {
                            "rushing_yards": player_data.get("RushingYards", 0) or 0,
                            "rushing_tds": player_data.get("RushingTouchdowns", 0) or 0,
                            "receiving_yards": player_data.get("ReceivingYards", 0)
                            or 0,
                            "receiving_tds": player_data.get("ReceivingTouchdowns", 0)
                            or 0,
                            "receptions": player_data.get("Receptions", 0) or 0,
                        }
                    )

                # Only add players with fantasy points
                if fantasy_points > 0:
                    players.append(player_record)

            except Exception as e:
                continue

        return pd.DataFrame(players)
