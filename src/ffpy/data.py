"""Data module for fantasy football projections."""

import pandas as pd
import streamlit as st
from typing import List, Dict, Optional
from ffpy.config import Config
from ffpy.integrations import ESPNIntegration, SportsDataIntegration
from ffpy.projections import HistoricalProjectionModel
from ffpy.database import FFPyDatabase


def get_sample_projections(week: int = 1) -> pd.DataFrame:
    """
    Get sample fantasy football projections for a given week.

    Args:
        week: NFL week number (1-18)

    Returns:
        DataFrame with player projections
    """
    # Sample data - in production, this would come from an API or database
    projections = [
        # Quarterbacks
        {
            "player": "Patrick Mahomes",
            "team": "KC",
            "position": "QB",
            "opponent": "DEN",
            "projected_points": 24.5,
            "passing_yards": 285,
            "passing_tds": 2.3,
            "rushing_yards": 18,
        },
        {
            "player": "Josh Allen",
            "team": "BUF",
            "position": "QB",
            "opponent": "MIA",
            "projected_points": 25.8,
            "passing_yards": 295,
            "passing_tds": 2.5,
            "rushing_yards": 42,
        },
        {
            "player": "Lamar Jackson",
            "team": "BAL",
            "position": "QB",
            "opponent": "CLE",
            "projected_points": 26.2,
            "passing_yards": 265,
            "passing_tds": 2.1,
            "rushing_yards": 68,
        },
        {
            "player": "Jalen Hurts",
            "team": "PHI",
            "position": "QB",
            "opponent": "NYG",
            "projected_points": 24.1,
            "passing_yards": 245,
            "passing_tds": 2.0,
            "rushing_yards": 55,
        },
        {
            "player": "Joe Burrow",
            "team": "CIN",
            "position": "QB",
            "opponent": "PIT",
            "projected_points": 22.3,
            "passing_yards": 275,
            "passing_tds": 2.2,
            "rushing_yards": 8,
        },
        # Running Backs
        {
            "player": "Christian McCaffrey",
            "team": "SF",
            "position": "RB",
            "opponent": "SEA",
            "projected_points": 22.4,
            "rushing_yards": 95,
            "rushing_tds": 0.8,
            "receiving_yards": 48,
            "receptions": 5.2,
        },
        {
            "player": "Derrick Henry",
            "team": "BAL",
            "position": "RB",
            "opponent": "CLE",
            "projected_points": 18.6,
            "rushing_yards": 105,
            "rushing_tds": 0.9,
            "receiving_yards": 15,
            "receptions": 1.5,
        },
        {
            "player": "Bijan Robinson",
            "team": "ATL",
            "position": "RB",
            "opponent": "CAR",
            "projected_points": 19.2,
            "rushing_yards": 88,
            "rushing_tds": 0.7,
            "receiving_yards": 42,
            "receptions": 4.1,
        },
        {
            "player": "Breece Hall",
            "team": "NYJ",
            "position": "RB",
            "opponent": "NE",
            "projected_points": 17.8,
            "rushing_yards": 78,
            "rushing_tds": 0.6,
            "receiving_yards": 38,
            "receptions": 3.8,
        },
        {
            "player": "Saquon Barkley",
            "team": "PHI",
            "position": "RB",
            "opponent": "NYG",
            "projected_points": 20.1,
            "rushing_yards": 92,
            "rushing_tds": 0.8,
            "receiving_yards": 35,
            "receptions": 3.5,
        },
        # Wide Receivers
        {
            "player": "Tyreek Hill",
            "team": "MIA",
            "position": "WR",
            "opponent": "BUF",
            "projected_points": 18.5,
            "receiving_yards": 95,
            "receiving_tds": 0.8,
            "receptions": 7.2,
        },
        {
            "player": "CeeDee Lamb",
            "team": "DAL",
            "position": "WR",
            "opponent": "WAS",
            "projected_points": 17.9,
            "receiving_yards": 88,
            "receiving_tds": 0.7,
            "receptions": 6.8,
        },
        {
            "player": "Amon-Ra St. Brown",
            "team": "DET",
            "position": "WR",
            "opponent": "CHI",
            "projected_points": 16.8,
            "receiving_yards": 82,
            "receiving_tds": 0.6,
            "receptions": 7.5,
        },
        {
            "player": "Justin Jefferson",
            "team": "MIN",
            "position": "WR",
            "opponent": "GB",
            "projected_points": 17.2,
            "receiving_yards": 92,
            "receiving_tds": 0.7,
            "receptions": 6.5,
        },
        {
            "player": "Ja'Marr Chase",
            "team": "CIN",
            "position": "WR",
            "opponent": "PIT",
            "projected_points": 16.5,
            "receiving_yards": 85,
            "receiving_tds": 0.6,
            "receptions": 5.8,
        },
        # Tight Ends
        {
            "player": "Travis Kelce",
            "team": "KC",
            "position": "TE",
            "opponent": "DEN",
            "projected_points": 13.2,
            "receiving_yards": 72,
            "receiving_tds": 0.6,
            "receptions": 6.2,
        },
        {
            "player": "Sam LaPorta",
            "team": "DET",
            "position": "TE",
            "opponent": "CHI",
            "projected_points": 11.8,
            "receiving_yards": 65,
            "receiving_tds": 0.5,
            "receptions": 5.8,
        },
        {
            "player": "George Kittle",
            "team": "SF",
            "position": "TE",
            "opponent": "SEA",
            "projected_points": 11.2,
            "receiving_yards": 62,
            "receiving_tds": 0.5,
            "receptions": 5.2,
        },
        {
            "player": "Mark Andrews",
            "team": "BAL",
            "position": "TE",
            "opponent": "CLE",
            "projected_points": 10.5,
            "receiving_yards": 58,
            "receiving_tds": 0.4,
            "receptions": 4.8,
        },
        {
            "player": "Evan Engram",
            "team": "JAC",
            "position": "TE",
            "opponent": "HOU",
            "projected_points": 9.8,
            "receiving_yards": 55,
            "receiving_tds": 0.3,
            "receptions": 5.5,
        },
    ]

    df = pd.DataFrame(projections)
    df["week"] = week

    return df


def get_historical_projections(week: int = 1, lookback_weeks: int = 4) -> pd.DataFrame:
    """
    Get projections based on historical player performance.

    Uses the HistoricalProjectionModel to generate projections by analyzing
    each player's recent actual performance from the database.

    Args:
        week: NFL week number to project (1-18)
        lookback_weeks: Number of past weeks to analyze (default: 4)

    Returns:
        DataFrame with player projections based on historical averages
    """
    try:
        model = HistoricalProjectionModel()
        season = Config.NFL_SEASON

        projections = model.generate_projections(
            season=season,
            week=week,
            lookback_weeks=lookback_weeks,
            recent_weight=0.6,  # Recent games weighted 60% more
        )

        if projections.empty:
            st.warning(
                f"No historical data available for week {week}. "
                "Make sure you have populated the database with historical stats."
            )
            return get_sample_projections(week)

        return projections

    except Exception as e:
        st.error(f"Error generating historical projections: {e}")
        return get_sample_projections(week)


@st.cache_data(ttl=Config.CACHE_TTL)
def get_projections(
    week: int = 1, use_real_data: bool = True, use_historical_model: bool = False
) -> pd.DataFrame:
    """
    Get fantasy football projections from configured source.

    This function is cached to avoid excessive API calls.
    Cache TTL is configured in .env (default: 1 hour).

    Args:
        week: NFL week number (1-18)
        use_real_data: If True, fetch from API. If False, use sample data.
        use_historical_model: If True, use historical performance-based projections.

    Returns:
        DataFrame with player projections
    """
    # Priority 1: Historical model (if enabled)
    if use_historical_model:
        return get_historical_projections(week=week)

    # Priority 2: Sample data (if real data disabled)
    if not use_real_data:
        return get_sample_projections(week)

    # Priority 3: API data
    # Determine which API to use
    api_provider = Config.get_api_provider()
    season = Config.NFL_SEASON

    # Try configured API
    df = pd.DataFrame()

    if api_provider == "sportsdata" and Config.is_sportsdata_configured():
        # Use SportsDataIO (paid, more reliable)
        integration = SportsDataIntegration(api_key=Config.SPORTSDATA_API_KEY)
        if integration.is_available():
            df = integration.get_projections(week=week, season=season)
            if not df.empty:
                return df

    # Fallback to ESPN (free, always available)
    integration = ESPNIntegration()
    df = integration.get_projections(week=week, season=season)

    # If API fails, use sample data
    if df.empty:
        st.warning("Unable to fetch real-time data. Using sample data.")
        return get_sample_projections(week)

    return df


def get_positions() -> List[str]:
    """Get list of available positions."""
    return ["QB", "RB", "WR", "TE"]


def filter_by_position(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """
    Filter projections by position.

    Args:
        df: DataFrame with projections
        position: Position to filter by (QB, RB, WR, TE)

    Returns:
        Filtered DataFrame
    """
    return df[df["position"] == position].sort_values("projected_points", ascending=False)


def get_top_n_players(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Get top N players by projected points.

    Args:
        df: DataFrame with projections
        n: Number of players to return

    Returns:
        DataFrame with top N players
    """
    return df.nlargest(n, "projected_points")
