"""
NFL play-by-play data loader using nflverse.

This module handles fetching, validating, and storing NFL play data
from the nflverse ecosystem via nflreadpy.
"""

import logging
from typing import Dict, Optional

import pandas as pd
import polars as pl

try:
    import nflreadpy as nfl
except ImportError:
    raise ImportError(
        "nflreadpy is not installed. Install it with: "
        "uv add 'nflreadpy @ git+https://github.com/nflverse/nflreadpy'"
    )

from ffpy.config import Config
from ffpy.database import FFPyDatabase

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
            print("Historical load complete!")
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
                    print("  [OK] Games already exist (skipped duplicates)")
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
                    print("  [OK] Plays already exist (skipped duplicates)")
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
                    print("  [OK] FTN charting already exists (skipped duplicates)")
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
        df = snaps_df.copy()

        # Normalize nflreadpy column names to DB schema.
        # nflreadpy returns 'player' but our schema expects 'player_name'.
        column_map = {
            "player": "player_name",
            "pfr_id": "pfr_player_id",
        }
        df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

        # Ensure player_id is treated as text (it's a GSIS ID string, not an integer)
        if "player_id" in df.columns:
            df["player_id"] = df["player_id"].astype(str)

        try:
            count = self.db.store_snap_counts(df, show_progress=verbose)
            if verbose:
                print(f"  [OK] Stored {count} snap count records")
            return count
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                if verbose:
                    print("  [OK] Snap counts already exist (skipped duplicates)")
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

    # ==================== ADVANCED STATS (Phase 1) ====================

    def compute_advanced_stats(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """
        Compute derived advanced player stats from plays + snap_counts + FTN.

        Runs per-player per-week aggregations against existing data and
        stores results into player_advanced_stats.

        Args:
            season: Season year
            verbose: Print progress messages

        Returns:
            Dict with row counts per data source
        """
        stats: Dict[str, int] = {"plays": 0, "snaps": 0, "ftn": 0}

        # --- Targets, air_yards, deep/red-zone/end-zone from plays ---
        if verbose:
            print(f"Computing advanced stats for {season} from plays...")

        plays_df = self.db.get_plays(season)

        if plays_df.empty:
            if verbose:
                print("  [WARN] No play data available for this season.")
            return stats

        # Filter to pass plays with receiver info
        pass_plays = plays_df[
            (plays_df["play_type"] == "pass") & (plays_df["receiver_player_name"].notna())
        ].copy()

        if pass_plays.empty:
            if verbose:
                print("  [WARN] No pass plays with receiver data.")
            return stats

        # Per-player weekly aggregates from plays
        play_agg = (
            pass_plays.groupby(["receiver_player_name", "week"])
            .agg(
                targets=("complete_pass", "count"),
                air_yards=("air_yards", "sum"),
                receptions=("complete_pass", "sum"),
                yards_after_catch=("yards_after_catch", "sum"),
                deep_targets=(
                    "pass_length",
                    lambda s: (s == "deep").sum(),
                ),
                red_zone_targets=(
                    "yardline_100",
                    lambda s: (s <= 20).sum(),
                ),
                end_zone_targets=(
                    "yardline_100",
                    lambda s: (s <= 10).sum(),
                ),
            )
            .reset_index()
        )

        play_agg.rename(columns={"receiver_player_name": "player_name"}, inplace=True)
        play_agg["avg_target_distance"] = play_agg["air_yards"] / play_agg["targets"].replace(0, float("nan"))
        play_agg["yards_after_catch_per_rec"] = play_agg["yards_after_catch"] / play_agg[
            "receptions"
        ].replace(0, float("nan"))

        # Pop first team/position per player from plays
        player_info = (
            pass_plays[["receiver_player_name", "posteam"]]
            .drop_duplicates(subset="receiver_player_name")
            .rename(columns={"receiver_player_name": "player_name", "posteam": "team"})
        )
        play_agg = play_agg.merge(player_info, on="player_name", how="left")

        play_agg["season"] = season
        stats["plays"] = len(play_agg)

        # --- Target share / air yards share per team-week ---
        team_week_totals = (
            pass_plays.groupby(["posteam", "week"])
            .agg(
                team_targets=("complete_pass", "count"),
                team_air_yards=("air_yards", "sum"),
            )
            .reset_index()
            .rename(columns={"posteam": "team"})
        )

        play_agg = play_agg.merge(team_week_totals, on=["team", "week"], how="left")
        play_agg["target_share"] = play_agg["targets"] / play_agg["team_targets"].replace(0, float("nan"))
        play_agg["air_yards_share"] = play_agg["air_yards"] / play_agg["team_air_yards"].replace(
            0, float("nan")
        )

        # --- Snap pct from snap_counts ---
        if verbose:
            print("Joining snap data...")
        try:
            snaps_query = """
                SELECT player_name, week, offense_pct AS snap_pct
                FROM snap_counts
                WHERE season = ? AND offense_pct IS NOT NULL
            """
            snaps_df = pd.read_sql(snaps_query, self.db.conn, params=[season])
            if not snaps_df.empty:
                play_agg = play_agg.merge(snaps_df, on=["player_name", "week"], how="left")
                stats["snaps"] = len(snaps_df)
        except Exception as e:
            if verbose:
                print(f"  [WARN] Could not load snap data: {e}")

        # --- First-read targets from FTN charting ---
        if verbose:
            print("Joining FTN charting data...")
        try:
            ftn_query = """
                SELECT fc.play_id, p.receiver_player_name AS player_name, p.week
                FROM ftn_charting fc
                JOIN plays p ON fc.play_id = p.play_id
                WHERE p.season = ? AND fc.read_thrown = 'first_read'
            """
            ftn_df = pd.read_sql(ftn_query, self.db.conn, params=[season])
            if not ftn_df.empty:
                first_read_agg = (
                    ftn_df.groupby(["player_name", "week"]).size().reset_index(name="first_read_targets")
                )
                play_agg = play_agg.merge(first_read_agg, on=["player_name", "week"], how="left")
                stats["ftn"] = len(ftn_df)
        except Exception as e:
            if verbose:
                print(f"  [WARN] Could not load FTN data: {e}")

        # --- Ensure columns exist even when source tables are empty ---
        for col, default in [
            ("snap_pct", 0.0),
            ("first_read_targets", 0),
            ("target_share", 0.0),
            ("air_yards_share", 0.0),
            ("avg_target_distance", 0.0),
            ("yards_after_catch_per_rec", 0.0),
        ]:
            if col not in play_agg.columns:
                play_agg[col] = default
            else:
                play_agg[col] = play_agg[col].fillna(default)

        # Build final columns matching player_advanced_stats schema
        out_cols = [
            "player_name",
            "team",
            "season",
            "week",
            "targets",
            "air_yards",
            "avg_target_distance",
            "target_share",
            "air_yards_share",
            "yards_after_catch_per_rec",
            "deep_targets",
            "red_zone_targets",
            "end_zone_targets",
            "snap_pct",
        ]
        if "first_read_targets" in play_agg.columns:
            out_cols.append("first_read_targets")

        result_df = play_agg[out_cols].copy()
        result_df = result_df.sort_values(["week", "player_name"]).reset_index(drop=True)

        stored = self.db.store_player_advanced_stats(result_df, season)
        if verbose:
            print(f"  [OK] Stored {stored} advanced stat rows")

        stats["stored"] = stored
        return stats

    # ==================== NEXT GEN STATS (Phase 2A) ====================

    def load_nextgen(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """
        Load Next Gen Stats for a season (passing, receiving, rushing).

        Args:
            season: Season year
            verbose: Print progress messages

        Returns:
            Dict with total rows stored
        """
        if verbose:
            print(f"Loading Next Gen Stats for {season}...")

        all_rows: list[pd.DataFrame] = []
        stat_types = ["passing", "receiving", "rushing"]

        for stat_type in stat_types:
            try:
                if verbose:
                    print(f"  Loading {stat_type} NGS...")
                raw = nfl.load_nextgen_stats(seasons=[season], stat_type=stat_type)
                if raw.is_empty():
                    continue
                pdf = raw.to_pandas()

                # Map to common schema
                out = pd.DataFrame()
                out["season"] = pdf.get("season", season)
                out["season_type"] = pdf.get("season_type", None)
                out["week"] = pdf.get("week", None)
                out["player_name"] = pdf.get("player_display_name", None)
                out["team"] = pdf.get("team_abbr", None)
                out["position"] = pdf.get("player_position", None)
                out["player_gsis_id"] = pdf.get("player_gsis_id", None)

                # Passing columns
                for col in [
                    "avg_time_to_throw",
                    "avg_completed_air_yards",
                    "avg_intended_air_yards",
                    "avg_air_yards_differential",
                    "aggressiveness",
                    "completion_percentage_above_expectation",
                ]:
                    out[col] = pdf.get(col, None)

                # Receiving columns
                for col in [
                    "avg_cushion",
                    "avg_separation",
                    "avg_yac",
                    "avg_expected_yac",
                    "avg_yac_above_expectation",
                ]:
                    out[col] = pdf.get(col, None)

                # Rushing columns
                for col in [
                    "expected_rush_yards",
                    "rush_yards_over_expected",
                    "rush_yards_over_expected_per_att",
                    "avg_time_to_los",
                    "efficiency",
                ]:
                    out[col] = pdf.get(col, None)

                all_rows.append(out)

            except Exception as e:
                if verbose:
                    print(f"  [WARN] Could not load {stat_type} NGS: {e}")

        if not all_rows:
            if verbose:
                print("  [WARN] No NGS data loaded")
            return {"stored": 0}

        combined = pd.concat(all_rows, ignore_index=True)
        stored = self.db.store_nextgen_stats(combined, season)

        if verbose:
            print(f"  [OK] Stored {stored} NGS rows")

        return {"stored": stored}

    # ==================== INJURIES (Phase 2B) ====================

    def load_injuries(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """
        Load player injury data for a season.

        Args:
            season: Season year
            verbose: Print progress messages

        Returns:
            Dict with total rows stored
        """
        if verbose:
            print(f"Loading injuries for {season}...")

        try:
            raw = nfl.load_injuries(seasons=[season])
        except Exception as e:
            if verbose:
                print(f"  [ERROR] Could not load injuries: {e}")
            return {"stored": 0}

        if raw.is_empty():
            if verbose:
                print("  [WARN] No injury data available")
            return {"stored": 0}

        pdf = raw.to_pandas()
        out = pd.DataFrame()
        out["player_name"] = pdf.get("full_name", None)
        out["team"] = pdf.get("team", None)
        out["season"] = pdf.get("season", season)
        out["week"] = pdf.get("week", None)
        out["practice_status"] = pdf.get("practice_status", None)
        out["injury_type"] = pdf.get("report_primary_injury", None)
        out["game_status"] = pdf.get("report_status", None)
        out["date_reported"] = pdf.get("date_modified", None)

        out = out.dropna(subset=["player_name"]).reset_index(drop=True)

        stored = self.db.store_player_injuries(out, season)

        if verbose:
            print(f"  [OK] Stored {stored} injury rows")

        return {"stored": stored}


    # ==================== PLAYER ROSTERS (Phase 1) ====================

    @staticmethod
    def _derive_draft_round(draft_number: Optional[int]) -> Optional[int]:
        """Derive draft round from overall pick number."""
        if draft_number is None or draft_number < 1:
            return None
        if draft_number <= 32:
            return 1
        if draft_number <= 64:
            return 2
        if draft_number <= 96:
            return 3
        if draft_number <= 128:
            return 4
        if draft_number <= 160:
            return 5
        if draft_number <= 192:
            return 6
        if draft_number <= 224:
            return 7
        return None

    def load_rosters(self, season: int, verbose: bool = True) -> Dict[str, int]:
        """
        Load player roster and bio data from nflreadpy.

        Args:
            season: Season year
            verbose: Print progress messages

        Returns:
            Dict with total rows stored
        """
        if verbose:
            print(f"Loading player rosters for {season}...")

        try:
            rosters = nfl.load_rosters(seasons=[season])
        except Exception as e:
            if verbose:
                print(f"  [ERROR] Could not load rosters: {e}")
            return {"stored": 0}

        if rosters.is_empty():
            if verbose:
                print("  [WARN] No roster data available")
            return {"stored": 0}

        pdf = rosters.to_pandas()
        out = pd.DataFrame()

        # nflreadpy columns: full_name, gsis_id, position, team, height,
        # weight, college, years_exp, headshot_url, draft_number, draft_club,
        # entry_year, rookie_year, birth_date, status
        out["gsis_id"] = pdf.get("gsis_id", None)
        out["player_name"] = pdf.get("full_name", None)
        out["position"] = pdf.get("position", None)
        out["team"] = pdf.get("team", None)
        out["season"] = season
        out["height"] = pdf.get("height", None)
        out["weight"] = pdf.get("weight", None)
        out["years_exp"] = pdf.get("years_exp", None)
        out["college"] = pdf.get("college", None)
        out["status"] = pdf.get("status", None)
        out["headshot_url"] = pdf.get("headshot_url", None)

        # Draft info
        draft_num = pdf.get("draft_number", None)
        out["draft_pick"] = draft_num
        out["draft_round"] = draft_num.apply(self._derive_draft_round) if draft_num is not None else None
        out["draft_team"] = pdf.get("draft_club", None)

        # Compute age from birth_date if available
        birth = pdf.get("birth_date", None)
        if birth is not None:
            import datetime
            ref = datetime.date(season, 9, 1)  # approximate season start
            out["age"] = birth.apply(
                lambda b: (ref - b.date()).days // 365 if hasattr(b, "date") and pd.notna(b) else None
            )
        else:
            out["age"] = None

        # Drop rows with no gsis_id or no player_name
        out = out.dropna(subset=["gsis_id", "player_name"]).reset_index(drop=True)

        if out.empty:
            if verbose:
                print("  [WARN] No roster records with valid gsis_id")
            return {"stored": 0}

        stored = self.db.store_player_rosters(out, season)
        if verbose:
            print(f"  [OK] Stored {stored} roster rows")

        return {"stored": stored}


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
