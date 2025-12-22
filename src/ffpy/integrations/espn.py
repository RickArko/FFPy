"""ESPN Fantasy Football API integration."""

import requests
import pandas as pd
from typing import Optional
from .base import BaseAPIIntegration


class ESPNIntegration(BaseAPIIntegration):
    """ESPN Fantasy Football API integration (free, unofficial)."""

    BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize ESPN integration (no API key required)."""
        super().__init__(api_key)

    def is_available(self) -> bool:
        """ESPN API is always available (no auth required)."""
        return True

    def get_actual_stats(self, week: int, season: int = 2024) -> pd.DataFrame:
        """
        Get actual game performance from ESPN.

        Args:
            week: NFL week number (1-18)
            season: NFL season year

        Returns:
            DataFrame with actual player performance
        """
        try:
            url = f"{self.BASE_URL}/seasons/{season}/segments/0/leaguedefaults/3"
            params = {"scoringPeriodId": week, "view": "kona_player_info"}

            # Add headers to avoid being blocked
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return self._parse_espn_data(
                data, week, stat_source_id=0
            )  # 0 = actual stats

        except Exception as e:
            print(f"ESPN API error fetching actuals: {e}")
            return pd.DataFrame()

    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame:
        """
        Get fantasy projections from ESPN.

        Args:
            week: NFL week number (1-18)
            season: NFL season year

        Returns:
            DataFrame with player projections
        """
        try:
            url = f"{self.BASE_URL}/seasons/{season}/segments/0/leaguedefaults/3"
            params = {"scoringPeriodId": week, "view": "kona_player_info"}

            # Add headers to avoid being blocked
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            return self._parse_espn_data(
                data, week, stat_source_id=1
            )  # 1 = projections

        except Exception as e:
            print(f"ESPN API error: {e}")
            return pd.DataFrame()

    def _parse_espn_data(
        self, data: dict, week: int, stat_source_id: int = 1
    ) -> pd.DataFrame:
        """
        Parse ESPN API response into standardized DataFrame.

        Args:
            data: Raw ESPN API response
            week: NFL week number

        Returns:
            Normalized DataFrame
        """
        players = []

        # ESPN returns players in 'players' key
        for player_data in data.get("players", []):
            try:
                player_info = player_data.get("player", {})

                # Extract basic info
                player_name = player_info.get("fullName", "")
                pro_team_id = player_info.get("proTeamId", 0)
                position = self._get_position(player_info.get("defaultPositionId", 0))

                # Skip defense/kicker for now
                if position not in ["QB", "RB", "WR", "TE"]:
                    continue

                # Get stats - ESPN uses stat IDs
                stats = player_data.get("player", {}).get("stats", [])
                extracted_stats = self._extract_stats(stats, week, stat_source_id)

                if not extracted_stats:
                    continue

                # Build player record (handle both actual and projected)
                if stat_source_id == 0:  # Actual stats
                    player_record = {
                        "player": player_name,
                        "team": self._get_team_abbr(pro_team_id),
                        "position": position,
                        "opponent": extracted_stats.get("opponent", "BYE"),
                        "actual_points": extracted_stats.get("actual_points", 0.0),
                        "week": week,
                    }
                else:  # Projected stats
                    player_record = {
                        "player": player_name,
                        "team": self._get_team_abbr(pro_team_id),
                        "position": position,
                        "opponent": extracted_stats.get("opponent", "BYE"),
                        "projected_points": extracted_stats.get(
                            "projected_points", 0.0
                        ),
                        "week": week,
                    }

                # Add position-specific stats
                if position == "QB":
                    player_record.update(
                        {
                            "passing_yards": projected_stats.get("passing_yards", 0),
                            "passing_tds": projected_stats.get("passing_tds", 0),
                            "rushing_yards": projected_stats.get("rushing_yards", 0),
                        }
                    )
                elif position in ["RB", "WR", "TE"]:
                    player_record.update(
                        {
                            "rushing_yards": projected_stats.get("rushing_yards", 0),
                            "rushing_tds": projected_stats.get("rushing_tds", 0),
                            "receiving_yards": projected_stats.get(
                                "receiving_yards", 0
                            ),
                            "receiving_tds": projected_stats.get("receiving_tds", 0),
                            "receptions": projected_stats.get("receptions", 0),
                        }
                    )

                players.append(player_record)

            except Exception as e:
                # Skip malformed player data
                continue

        return pd.DataFrame(players)

    def _extract_stats(self, stats: list, week: int, stat_source_id: int) -> dict:
        """
        Extract stats for the given week.

        Args:
            stats: List of stat entries from ESPN API
            week: Week number
            stat_source_id: 0 = actual stats, 1 = projections

        Returns:
            Dictionary of stats
        """
        for stat_entry in stats:
            # Look for stats matching the source ID and week
            if (
                stat_entry.get("statSourceId") == stat_source_id
                and stat_entry.get("scoringPeriodId") == week
            ):
                raw_stats = stat_entry.get("stats", {})

                # ESPN stat IDs (same for both actual and projected)
                stats_dict = {
                    "passing_yards": raw_stats.get("3", 0),
                    "passing_tds": raw_stats.get("4", 0),
                    "interceptions": raw_stats.get("20", 0),
                    "rushing_yards": raw_stats.get("24", 0),
                    "rushing_tds": raw_stats.get("25", 0),
                    "receiving_yards": raw_stats.get("42", 0),
                    "receiving_tds": raw_stats.get("43", 0),
                    "receptions": raw_stats.get("53", 0),
                }

                # Add points field based on stat type
                if stat_source_id == 0:
                    stats_dict["actual_points"] = raw_stats.get("0", 0.0)
                else:
                    stats_dict["projected_points"] = raw_stats.get("0", 0.0)

                return stats_dict

        return {}

    # Keep old method for backwards compatibility
    def _extract_projected_stats(self, stats: list, week: int) -> dict:
        """Extract projected stats for the given week (deprecated - use _extract_stats)."""
        return self._extract_stats(stats, week, stat_source_id=1)

    def _get_position(self, position_id: int) -> str:
        """Convert ESPN position ID to abbreviation."""
        positions = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
        return positions.get(position_id, "UNK")

    def _get_team_abbr(self, team_id: int) -> str:
        """Convert ESPN team ID to abbreviation."""
        teams = {
            1: "ATL",
            2: "BUF",
            3: "CHI",
            4: "CIN",
            5: "CLE",
            6: "DAL",
            7: "DEN",
            8: "DET",
            9: "GB",
            10: "TEN",
            11: "IND",
            12: "KC",
            13: "LV",
            14: "LAR",
            15: "MIA",
            16: "MIN",
            17: "NE",
            18: "NO",
            19: "NYG",
            20: "NYJ",
            21: "PHI",
            22: "ARI",
            23: "PIT",
            24: "LAC",
            25: "SF",
            26: "SEA",
            27: "TB",
            28: "WAS",
            29: "CAR",
            30: "JAX",
            33: "BAL",
            34: "HOU",
        }
        return teams.get(team_id, "FA")
