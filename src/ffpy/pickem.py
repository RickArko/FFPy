"""
NFL Pick'em Competition Analyzer.

This module helps with weekly NFL pick'em competitions by providing:
- Game schedules and matchups
- Win probability predictions
- Confidence rankings
- Historical performance analysis
- Optimal pick strategies
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests


@dataclass
class NFLGame:
    """Represents an NFL game."""

    game_id: str
    week: int
    season: int
    home_team: str
    away_team: str
    home_abbrev: str
    away_abbrev: str
    game_time: Optional[datetime] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    spread: Optional[float] = None  # Positive = home favored
    over_under: Optional[float] = None
    home_win_prob: Optional[float] = None
    is_final: bool = False

    def get_favorite(self) -> Tuple[str, float]:
        """
        Get the favored team and spread.

        Returns:
            Tuple of (team_abbrev, spread_magnitude)
        """
        if self.spread is None:
            return self.home_abbrev, 0.0

        if self.spread > 0:
            return self.home_abbrev, abs(self.spread)
        else:
            return self.away_abbrev, abs(self.spread)

    def get_winner(self) -> Optional[str]:
        """Get the winning team (if game is final)."""
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None

        if self.home_score > self.away_score:
            return self.home_abbrev
        elif self.away_score > self.home_score:
            return self.away_abbrev
        else:
            return "TIE"


class PickemAnalyzer:
    """Analyze NFL games for pick'em competitions."""

    # ESPN NFL team IDs
    TEAM_IDS = {
        "ARI": 22,
        "ATL": 1,
        "BAL": 33,
        "BUF": 2,
        "CAR": 29,
        "CHI": 3,
        "CIN": 4,
        "CLE": 5,
        "DAL": 6,
        "DEN": 7,
        "DET": 8,
        "GB": 9,
        "HOU": 34,
        "IND": 11,
        "JAX": 30,
        "KC": 12,
        "LV": 13,
        "LAC": 24,
        "LAR": 14,
        "MIA": 15,
        "MIN": 16,
        "NE": 17,
        "NO": 18,
        "NYG": 19,
        "NYJ": 20,
        "PHI": 21,
        "PIT": 23,
        "SF": 25,
        "SEA": 26,
        "TB": 27,
        "TEN": 10,
        "WAS": 28,
    }

    # Reverse mapping
    ID_TO_TEAM = {v: k for k, v in TEAM_IDS.items()}

    def __init__(self, season: int = 2025):
        """
        Initialize pick'em analyzer.

        Args:
            season: NFL season year (default: 2025)
        """
        self.season = season

    def get_weekly_games(self, week: int) -> List[NFLGame]:
        """
        Get all NFL games for a specific week.

        Args:
            week: NFL week number (1-18)

        Returns:
            List of NFLGame objects
        """
        try:
            # ESPN NFL scoreboard API
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            params = {
                "seasontype": 2,  # Regular season
                "week": week,
                "dates": self.season,
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            games = []
            for event in data.get("events", []):
                game = self._parse_espn_game(event, week)
                if game:
                    games.append(game)

            return games

        except Exception as e:
            print(f"Error fetching games: {e}")
            return []

    def _parse_espn_game(self, event: Dict, week: int) -> Optional[NFLGame]:
        """Parse ESPN game data into NFLGame object."""
        try:
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])

            if len(competitors) != 2:
                return None

            # Home team is typically competitors[0], away is [1]
            home = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
            away = competitors[1] if competitors[1].get("homeAway") == "away" else competitors[0]

            # Parse teams
            home_team = home.get("team", {}).get("displayName", "Unknown")
            away_team = away.get("team", {}).get("displayName", "Unknown")
            home_abbrev = home.get("team", {}).get("abbreviation", "UNK")
            away_abbrev = away.get("team", {}).get("abbreviation", "UNK")

            # Parse scores (if available)
            home_score = None
            away_score = None
            if home.get("score"):
                home_score = int(home.get("score", 0))
                away_score = int(away.get("score", 0))

            # Game status
            is_final = competition.get("status", {}).get("type", {}).get("completed", False)

            # Odds (if available)
            spread = None
            over_under = None
            odds = competition.get("odds", [])
            if odds:
                spread_line = odds[0].get("details", "")
                over_under_line = odds[0].get("overUnder")

                # Parse spread (e.g., "KC -7" means KC favored by 7)
                if spread_line:
                    parts = spread_line.split()
                    if len(parts) >= 2:
                        try:
                            spread = float(parts[1])
                            # Normalize to home team perspective
                            if parts[0] == away_abbrev:
                                spread = -spread
                        except ValueError:
                            pass

                if over_under_line:
                    over_under = float(over_under_line)

            # Win probability (if available)
            home_win_prob = None
            if "predictor" in competition:
                home_win_prob = competition["predictor"].get("homeTeam", {}).get("gameProjection", None)

            # Game time
            game_time = None
            if event.get("date"):
                try:
                    game_time = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError):
                    pass

            return NFLGame(
                game_id=event.get("id", ""),
                week=week,
                season=self.season,
                home_team=home_team,
                away_team=away_team,
                home_abbrev=home_abbrev,
                away_abbrev=away_abbrev,
                game_time=game_time,
                home_score=home_score,
                away_score=away_score,
                spread=spread,
                over_under=over_under,
                home_win_prob=home_win_prob,
                is_final=is_final,
            )

        except Exception as e:
            print(f"Error parsing game: {e}")
            return None

    def calculate_confidence_rankings(self, games: List[NFLGame]) -> pd.DataFrame:
        """
        Calculate confidence rankings for pick'em.

        Ranks games by certainty of outcome (most confident = highest rank).

        Args:
            games: List of NFLGame objects

        Returns:
            DataFrame with games ranked by confidence
        """
        game_data = []

        for game in games:
            favorite, spread_magnitude = game.get_favorite()

            # Calculate confidence score
            # Higher spread = more confident pick
            confidence_score = spread_magnitude if spread_magnitude else 0

            # Adjust by win probability if available
            if game.home_win_prob:
                prob = game.home_win_prob if favorite == game.home_abbrev else (1 - game.home_win_prob)
                # Weight win prob into confidence
                confidence_score = (confidence_score * 0.6) + (prob * 100 * 0.4)

            game_data.append(
                {
                    "matchup": f"{game.away_abbrev} @ {game.home_abbrev}",
                    "favorite": favorite,
                    "spread": spread_magnitude,
                    "win_prob": game.home_win_prob,
                    "confidence_score": confidence_score,
                    "pick": favorite,
                    "game": game,
                }
            )

        df = pd.DataFrame(game_data)

        # Sort by confidence score (highest = most confident)
        df = df.sort_values("confidence_score", ascending=False)

        # Assign confidence points (highest confidence = highest points)
        df["confidence_points"] = range(len(df), 0, -1)

        return df

    def get_upset_candidates(self, games: List[NFLGame], threshold: float = 3.0) -> pd.DataFrame:
        """
        Identify potential upset games (close matchups).

        Args:
            games: List of NFLGame objects
            threshold: Spread threshold for "close game" (default: 3 points)

        Returns:
            DataFrame with upset candidates
        """
        upsets = []

        for game in games:
            favorite, spread = game.get_favorite()

            # Consider it an upset candidate if spread is small
            if spread is not None and spread <= threshold:
                underdog = game.away_abbrev if favorite == game.home_abbrev else game.home_abbrev

                upsets.append(
                    {
                        "matchup": f"{game.away_abbrev} @ {game.home_abbrev}",
                        "favorite": favorite,
                        "underdog": underdog,
                        "spread": spread,
                        "upset_probability": min((threshold - spread) / threshold, 0.5),
                    }
                )

        return pd.DataFrame(upsets).sort_values("spread", ascending=True)

    def simulate_pickem_strategy(self, games: List[NFLGame], strategy: str = "favorites") -> Dict:
        """
        Simulate a pick'em strategy.

        Args:
            games: List of NFLGame objects
            strategy: "favorites" (pick all favorites) or "confidence" (rank by spread)

        Returns:
            Dict with picks and confidence rankings
        """
        if strategy == "favorites":
            picks = []
            for game in games:
                favorite, spread = game.get_favorite()
                picks.append(
                    {
                        "matchup": f"{game.away_abbrev} @ {game.home_abbrev}",
                        "pick": favorite,
                        "spread": spread,
                        "reasoning": f"Favored by {spread:.1f} points",
                    }
                )
            return {"strategy": "All Favorites", "picks": picks}

        elif strategy == "confidence":
            df = self.calculate_confidence_rankings(games)
            picks = []
            for _, row in df.iterrows():
                picks.append(
                    {
                        "matchup": row["matchup"],
                        "pick": row["pick"],
                        "confidence": int(row["confidence_points"]),
                        "spread": row["spread"],
                        "reasoning": f"Confidence: {row['confidence_score']:.1f}",
                    }
                )
            return {"strategy": "Confidence-Based", "picks": picks}

        return {}

    def format_weekly_picks(self, games: List[NFLGame], include_confidence: bool = True) -> str:
        """
        Format weekly picks for easy copy/paste.

        Args:
            games: List of NFLGame objects
            include_confidence: Include confidence rankings

        Returns:
            Formatted string with picks
        """
        if include_confidence:
            df = self.calculate_confidence_rankings(games)

            lines = ["WEEKLY PICKS (with Confidence Rankings)", "=" * 60]

            for idx, row in df.iterrows():
                confidence = int(row["confidence_points"])
                matchup = row["matchup"]
                pick = row["pick"]
                spread = row["spread"]

                line = f"{confidence:2d}. {matchup:20} → Pick: {pick:4} (Spread: {spread:.1f})"
                lines.append(line)
        else:
            lines = ["WEEKLY PICKS (Straight Up)", "=" * 60]

            for game in games:
                favorite, spread = game.get_favorite()
                matchup = f"{game.away_abbrev} @ {game.home_abbrev}"
                line = f"{matchup:20} → Pick: {favorite:4} (Spread: {spread:.1f})"
                lines.append(line)

        lines.append("=" * 60)
        return "\n".join(lines)


def create_sample_pickem_data(week: int = 15) -> List[NFLGame]:
    """
    Create sample pick'em data for testing.

    ⚠️ WARNING: This is FAKE data for testing only!
    Real matchups will be different.

    Args:
        week: Week number

    Returns:
        List of sample NFLGame objects with fictional matchups
    """
    print("⚠️  Using SAMPLE DATA (not real games!)")

    sample_games = [
        NFLGame(
            "sample_1",
            week,
            2024,
            "Kansas City Chiefs",
            "Las Vegas Raiders",
            "KC",
            "LV",
            spread=7.5,
            home_win_prob=0.75,
        ),
        NFLGame(
            "sample_2",
            week,
            2024,
            "Buffalo Bills",
            "Miami Dolphins",
            "BUF",
            "MIA",
            spread=3.0,
            home_win_prob=0.60,
        ),
        NFLGame(
            "sample_3",
            week,
            2024,
            "San Francisco 49ers",
            "Arizona Cardinals",
            "SF",
            "ARI",
            spread=10.5,
            home_win_prob=0.82,
        ),
        NFLGame(
            "sample_4",
            week,
            2024,
            "Baltimore Ravens",
            "Jacksonville Jaguars",
            "BAL",
            "JAX",
            spread=6.5,
            home_win_prob=0.72,
        ),
        NFLGame(
            "sample_5",
            week,
            2024,
            "Dallas Cowboys",
            "Philadelphia Eagles",
            "DAL",
            "PHI",
            spread=-2.5,
            home_win_prob=0.45,
        ),
        NFLGame(
            "sample_6",
            week,
            2024,
            "Detroit Lions",
            "Chicago Bears",
            "DET",
            "CHI",
            spread=4.5,
            home_win_prob=0.65,
        ),
        NFLGame(
            "sample_7",
            week,
            2024,
            "Green Bay Packers",
            "Minnesota Vikings",
            "GB",
            "MIN",
            spread=-1.0,
            home_win_prob=0.48,
        ),
        NFLGame(
            "sample_8",
            week,
            2024,
            "Cincinnati Bengals",
            "Pittsburgh Steelers",
            "CIN",
            "PIT",
            spread=2.5,
            home_win_prob=0.58,
        ),
    ]

    return sample_games
