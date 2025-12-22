"""
NFL play-by-play data loader using nflverse.

This module handles fetching, validating, and storing NFL play data
from the nflverse ecosystem via nflreadpy.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict
import pandas as pd
import polars as pl

try:
    import nflreadpy as nfl
except ImportError:
    raise ImportError(
        "nflreadpy is not installed. Install it with: "
        "uv add 'nflreadpy @ git+https://github.com/nflverse/nflreadpy'"
    )

from ffpy.database import FFPyDatabase
from ffpy.config import Config

logger = logging.getLogger(__name__)


class NFLVerseLoader:
    """Load NFL play-by-play data from nflverse."""

    def __init__(self, db: Optional[FFPyDatabase] = None):
        """
        Initialize the loader.

        Args:
            db: Optional database instance. If None, creates new connection.
        """
        self.db = db
        self._own_db = db is None

        if self._own_db:
            self.db = FFPyDatabase()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_db and self.db:
            self.db.close()

    def load_season(
        self,
        season: int,
        include_ftn: bool = True,
        include_snaps: bool = True,
        verbose: bool = True,
    ) -> Dict[str, int]:
        """
        Load complete season data.

        Args:
            season: NFL season year
            include_ftn: Include FTN charting (only 2022+)
            include_snaps: Include snap counts (only 2012+)
            verbose: Print progress messages

        Returns:
            Dictionary with load statistics
        """
        stats = {"plays": 0, "games": 0, "ftn": 0, "snaps": 0}
        load_id = self.db.log_data_load("pbp", season)

        try:
            # Load play-by-play data
            if verbose:
                logger.info(f"Loading play-by-play data for {season}...")
                print(f"Loading play-by-play data for {season}...")

            pbp = nfl.load_pbp(seasons=[season])

            # Convert to pandas for database compatibility
            if verbose:
                print(f"Converting {len(pbp)} plays to pandas...")
            pbp_df = pbp.to_pandas()

            # Extract and store games first (for foreign key)
            if verbose:
                print("Extracting game metadata...")
            games = self._extract_games(pbp_df)
            stats["games"] = self._store_games(games, verbose)

            # Store plays with progress bar
            stats["plays"] = self._store_plays(pbp_df, verbose)

            # Load FTN charting if requested and available
            if include_ftn and season >= 2022:
                try:
                    if verbose:
                        print(f"Loading FTN charting data for {season}...")
                    ftn = nfl.load_ftn_charting(seasons=[season])
                    ftn_df = ftn.to_pandas()
                    stats["ftn"] = self._store_ftn_charting(ftn_df, verbose)
                except Exception as e:
                    logger.warning(f"Could not load FTN data: {e}")
                    if verbose:
                        print(f"Warning: Could not load FTN data: {e}")

            # Load snap counts if requested and available
            if include_snaps and season >= 2012:
                try:
                    if verbose:
                        print(f"Loading snap counts for {season}...")
                    snaps = nfl.load_snap_counts(seasons=[season])
                    snaps_df = snaps.to_pandas()
                    stats["snaps"] = self._store_snap_counts(snaps_df, verbose)
                except Exception as e:
                    logger.warning(f"Could not load snap counts: {e}")
                    if verbose:
                        print(f"Warning: Could not load snap counts: {e}")

            # Mark load as completed
            self.db.update_data_load(load_id, "completed", stats["plays"])

            if verbose:
                print(f"\nSuccessfully loaded {season} season:")
                print(f"  - {stats['games']} games")
                print(f"  - {stats['plays']} plays")
                if stats["ftn"] > 0:
                    print(f"  - {stats['ftn']} FTN charting records")
                if stats["snaps"] > 0:
                    print(f"  - {stats['snaps']} snap count records")

        except Exception as e:
            logger.error(f"Error loading season {season}: {e}")
            self.db.update_data_load(load_id, "failed", 0, str(e))
            raise

        return stats

    def load_historical(
        self,
        start_season: int,
        end_season: Optional[int] = None,
        include_ftn: bool = True,
        include_snaps: bool = True,
        verbose: bool = True,
    ) -> Dict[str, int]:
        """
        Load multiple seasons of historical data.

        Args:
            start_season: First season to load
            end_season: Last season to load (defaults to current NFL season)
            include_ftn: Include FTN charting (only 2022+)
            include_snaps: Include snap counts (only 2012+)
            verbose: Print progress messages

        Returns:
            Dictionary with total load statistics
        """
        if end_season is None:
            end_season = Config.NFL_SEASON

        total_stats = {"plays": 0, "games": 0, "ftn": 0, "snaps": 0}

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"Loading {end_season - start_season + 1} seasons ({start_season}-{end_season})")
            print(f"{'=' * 60}\n")

        for season in range(start_season, end_season + 1):
            stats = self.load_season(season, include_ftn, include_snaps, verbose)

            for key in total_stats:
                total_stats[key] += stats[key]

            if verbose:
                print()  # Blank line between seasons

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"Historical load complete!")
            print(f"  Total games: {total_stats['games']}")
            print(f"  Total plays: {total_stats['plays']}")
            if total_stats["ftn"] > 0:
                print(f"  Total FTN records: {total_stats['ftn']}")
            if total_stats["snaps"] > 0:
                print(f"  Total snap records: {total_stats['snaps']}")
            print(f"{'=' * 60}\n")

        return total_stats

    def update_current_season(self, verbose: bool = True) -> Dict[str, int]:
        """
        Incrementally update current season with new games only.

        Args:
            verbose: Print progress messages

        Returns:
            Dictionary with update statistics
        """
        season = Config.NFL_SEASON

        if verbose:
            print(f"Checking for new games in {season} season...")

        # Get latest game_id in database
        latest_game = self.db.get_latest_game_id(season)

        if verbose and latest_game:
            print(f"Latest game in database: {latest_game}")

        # Load current season
        pbp = nfl.load_pbp(seasons=[season])

        # Filter to only new games
        if latest_game:
            pbp = pbp.filter(pl.col("game_id") > latest_game)

        if pbp.is_empty() or len(pbp) == 0:
            if verbose:
                print("No new games to update.")
            return {"plays": 0, "games": 0}

        pbp_df = pbp.to_pandas()

        if verbose:
            print(f"Found {len(pbp_df)} new plays to add")

        # Store new data
        games = self._extract_games(pbp_df)
        games_stored = self._store_games(games, verbose)
        plays_stored = self._store_plays(pbp_df, verbose)

        if verbose:
            print(f"Updated: {games_stored} games, {plays_stored} plays")

        return {"plays": plays_stored, "games": games_stored}

    def _extract_games(self, pbp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract unique game metadata from play data.

        Args:
            pbp_df: Play-by-play DataFrame

        Returns:
            DataFrame with game-level data
        """
        # Group by game_id and take first occurrence of game-level fields
        game_fields = [
            "game_id",
            "old_game_id",
            "season",
            "season_type",
            "week",
            "game_date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "roof",
            "surface",
            "temp",
            "wind",
            "spread_line",
            "total_line",
            "location",
            "stadium",
        ]

        # Filter to only fields that exist
        available_fields = [f for f in game_fields if f in pbp_df.columns]

        games = pbp_df[available_fields].drop_duplicates(subset=["game_id"]).copy()

        return games

    def _store_games(self, games_df: pd.DataFrame, verbose: bool = True) -> int:
        """
        Store game metadata in database.

        Args:
            games_df: DataFrame with game data
            verbose: Print progress

        Returns:
            Number of games stored
        """
        try:
            count = self.db.store_games(games_df)
            if verbose:
                print(f"  [OK] Stored {count} games")
            return count
        except Exception as e:
            # Handle duplicate games (already exists)
            if "UNIQUE constraint failed" in str(e):
                if verbose:
                    print(f"  [OK] Games already exist (skipped duplicates)")
                return 0
            else:
                raise

    def _store_plays(self, pbp_df: pd.DataFrame, verbose: bool = True) -> int:
        """
        Store play-by-play data in database.

        Args:
            pbp_df: Play-by-play DataFrame
            verbose: Print progress

        Returns:
            Number of plays stored
        """
        try:
            count = self.db.store_plays(pbp_df, show_progress=verbose)
            if verbose:
                print(f"  [OK] Stored {count} plays")
            return count
        except Exception as e:
            # Handle duplicate plays (already exists)
            if "UNIQUE constraint failed" in str(e):
                if verbose:
                    print(f"  [OK] Plays already exist (skipped duplicates)")
                return 0
            else:
                raise

    def _store_ftn_charting(self, ftn_df: pd.DataFrame, verbose: bool = True) -> int:
        """
        Store FTN charting data in database.

        Args:
            ftn_df: FTN charting DataFrame
            verbose: Print progress

        Returns:
            Number of records stored
        """
        try:
            count = self.db.store_ftn_charting(ftn_df, show_progress=verbose)
            if verbose:
                print(f"  [OK] Stored {count} FTN charting records")
            return count
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                if verbose:
                    print(f"  [OK] FTN charting already exists (skipped duplicates)")
                return 0
            else:
                raise

    def _store_snap_counts(self, snaps_df: pd.DataFrame, verbose: bool = True) -> int:
        """
        Store snap count data in database.

        Args:
            snaps_df: Snap counts DataFrame
            verbose: Print progress

        Returns:
            Number of records stored
        """
        try:
            count = self.db.store_snap_counts(snaps_df, show_progress=verbose)
            if verbose:
                print(f"  [OK] Stored {count} snap count records")
            return count
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                if verbose:
                    print(f"  [OK] Snap counts already exist (skipped duplicates)")
                return 0
            else:
                raise

    def validate_data_quality(self, season: int) -> Dict[str, any]:
        """
        Validate data quality for a loaded season.

        Args:
            season: Season to validate

        Returns:
            Dictionary with validation results
        """
        results = {
            "season": season,
            "total_plays": 0,
            "total_games": 0,
            "missing_player_ids": 0,
            "missing_epa": 0,
            "invalid_downs": 0,
            "quality_score": 0.0,
        }

        # Get plays for season
        plays = self.db.get_plays(season)

        if plays.empty:
            return results

        results["total_plays"] = len(plays)

        # Count unique games
        results["total_games"] = plays["game_id"].nunique()

        # Check for missing player IDs on relevant plays
        pass_plays = plays[plays["play_type"] == "pass"]
        if len(pass_plays) > 0:
            results["missing_player_ids"] = pass_plays["passer_player_id"].isna().sum()

        # Check for missing EPA values
        results["missing_epa"] = plays["epa"].isna().sum()

        # Check for invalid downs
        if "down" in plays.columns:
            results["invalid_downs"] = (
                ~plays["down"].between(1, 4, inclusive="both") & plays["down"].notna()
            ).sum()

        # Calculate quality score (0-100)
        total_checks = results["total_plays"]
        if total_checks > 0:
            issues = results["missing_player_ids"] + results["missing_epa"] + results["invalid_downs"]
            results["quality_score"] = max(0, 100 - (issues / total_checks * 100))

        return results


def setup_database(db_path: Optional[str] = None) -> FFPyDatabase:
    """
    Initialize database with play-by-play schema.

    Args:
        db_path: Optional custom database path

    Returns:
        Initialized database instance
    """
    db = FFPyDatabase(db_path)

    # Run play-by-play migration
    print("Running play-by-play migration...")
    db.run_migration("002_play_by_play_schema.sql")
    print("[OK] Migration complete")

    return db
