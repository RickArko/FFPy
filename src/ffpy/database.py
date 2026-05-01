"""Database operations for FFPy - Focus on historical actual stats."""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import pandas as pd
from datetime import datetime, date
import os


class FFPyDatabase:
    """SQLite database for storing historical player stats."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            db_path: Custom database path. If None, uses config default.
        """
        if db_path is None:
            # Import here to avoid circular dependency
            from ffpy.config import Config

            db_path = Config.DATABASE_PATH

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Access columns by name

        # Initialize schema
        self.init_database()

    def init_database(self):
        """Create tables if they don't exist.

        Runs 001 (core: players, actual_stats, projections, api_requests) and 003
        (backtest: backtest_runs, backtest_picks). The 002 pbp schema is opt-in
        via run_migration('002_play_by_play_schema.sql') because it's heavy and
        not every workflow needs it.
        """
        migrations_dir = Path(__file__).parent / "migrations"
        for name in ("001_initial_schema.sql", "003_backtest_schema.sql"):
            with open(migrations_dir / name, "r") as f:
                self.conn.executescript(f.read())
        self.conn.commit()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ==================== PLAYER METHODS ====================

    def get_or_create_player(self, name: str, team: str, position: str, nfl_id: Optional[str] = None) -> int:
        """
        Get player_id or create new player.

        Args:
            name: Player name
            team: Team abbreviation
            position: Position (QB, RB, WR, TE)
            nfl_id: Optional unique NFL/ESPN ID

        Returns:
            player_id
        """
        cursor = self.conn.cursor()

        # Try to find existing player
        if nfl_id:
            cursor.execute("SELECT player_id FROM players WHERE nfl_id = ?", (nfl_id,))
        else:
            cursor.execute(
                "SELECT player_id FROM players WHERE name = ? AND position = ?",
                (name, position),
            )

        row = cursor.fetchone()

        if row:
            player_id = row["player_id"]

            # Update team if changed
            cursor.execute(
                "UPDATE players SET team = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ?",
                (team, player_id),
            )
            self.conn.commit()

            return player_id

        # Create new player
        cursor.execute(
            """INSERT INTO players (name, team, position, nfl_id)
               VALUES (?, ?, ?, ?)""",
            (name, team, position, nfl_id),
        )
        self.conn.commit()

        return cursor.lastrowid

    # ==================== ACTUAL STATS METHODS ====================

    def store_actual_stats(self, df: pd.DataFrame, season: int, week: int, source: str = "espn"):
        """
        Store actual game stats from DataFrame.

        Args:
            df: DataFrame with actual stats
            season: NFL season year
            week: Week number (1-18)
            source: Data source identifier
        """
        cursor = self.conn.cursor()

        for _, row in df.iterrows():
            # Get or create player
            player_id = self.get_or_create_player(
                name=row["player"],
                team=row["team"],
                position=row["position"],
                nfl_id=row.get("nfl_id"),
            )

            # Insert or replace actual stats
            cursor.execute(
                """INSERT OR REPLACE INTO actual_stats (
                    player_id, season, week,
                    actual_points,
                    passing_yards, passing_tds, interceptions,
                    rushing_yards, rushing_tds,
                    receiving_yards, receiving_tds, receptions,
                    opponent, home_away, game_date, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    season,
                    week,
                    row.get("actual_points", 0),
                    row.get("passing_yards", 0),
                    row.get("passing_tds", 0),
                    row.get("interceptions", 0),
                    row.get("rushing_yards", 0),
                    row.get("rushing_tds", 0),
                    row.get("receiving_yards", 0),
                    row.get("receiving_tds", 0),
                    row.get("receptions", 0),
                    row.get("opponent", ""),
                    row.get("home_away", ""),
                    row.get("game_date"),
                    source,
                ),
            )

        self.conn.commit()

    def get_actual_stats(
        self, season: int, week: Optional[int] = None, position: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Retrieve actual stats from database.

        Args:
            season: NFL season year
            week: Optional week filter
            position: Optional position filter

        Returns:
            DataFrame with actual stats
        """
        query = """
            SELECT
                p.name as player,
                p.team,
                p.position,
                a.season,
                a.week,
                a.actual_points,
                a.passing_yards,
                a.passing_tds,
                a.interceptions,
                a.rushing_yards,
                a.rushing_tds,
                a.receiving_yards,
                a.receiving_tds,
                a.receptions,
                a.opponent,
                a.home_away,
                a.game_date
            FROM actual_stats a
            JOIN players p ON a.player_id = p.player_id
            WHERE a.season = ?
        """

        params = [season]

        if week is not None:
            query += " AND a.week = ?"
            params.append(week)

        if position:
            query += " AND p.position = ?"
            params.append(position)

        query += " ORDER BY a.actual_points DESC"

        return pd.read_sql(query, self.conn, params=params)

    def get_player_history(self, player_name: str, num_weeks: int = 8) -> pd.DataFrame:
        """
        Get player's recent actual performance history.

        Args:
            player_name: Player name
            num_weeks: Number of recent weeks to fetch

        Returns:
            DataFrame with player's history
        """
        query = """
            SELECT
                p.name as player,
                p.team,
                p.position,
                a.season,
                a.week,
                a.actual_points,
                a.passing_yards,
                a.passing_tds,
                a.rushing_yards,
                a.rushing_tds,
                a.receiving_yards,
                a.receiving_tds,
                a.receptions,
                a.opponent
            FROM actual_stats a
            JOIN players p ON a.player_id = p.player_id
            WHERE p.name = ?
            ORDER BY a.season DESC, a.week DESC
            LIMIT ?
        """

        return pd.read_sql(query, self.conn, params=[player_name, num_weeks])

    # ==================== API REQUEST TRACKING ====================

    def check_api_request(self, source: str, season: int, week: int, request_type: str = "actuals") -> bool:
        """
        Check if we already fetched data for this request today.

        Args:
            source: API source
            season: Season year
            week: Week number
            request_type: 'actuals' or 'projections'

        Returns:
            True if data exists, False if we need to fetch
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT 1 FROM api_requests
               WHERE source = ? AND season = ? AND week = ?
               AND request_type = ? AND DATE(created_at) = DATE('now')
               AND success = 1""",
            (source, season, week, request_type),
        )

        return cursor.fetchone() is not None

    def log_api_request(
        self,
        source: str,
        season: int,
        week: int,
        request_type: str,
        success: bool,
        error: Optional[str] = None,
    ):
        """Log API request to database."""
        cursor = self.conn.cursor()

        cursor.execute(
            """INSERT INTO api_requests (source, season, week, request_type, success, error_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source, season, week, request_type, success, error),
        )

        self.conn.commit()

    # ==================== EXPORT / BACKUP ====================

    def export_to_csv(self, output_dir: str = "backups"):
        """
        Export all tables to CSV for backup.

        Args:
            output_dir: Directory to save CSV files
        """
        backup_path = Path(output_dir)
        backup_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Export each table
        tables = ["players", "actual_stats", "projections", "api_requests"]

        for table in tables:
            df = pd.read_sql(f"SELECT * FROM {table}", self.conn)
            csv_file = backup_path / f"{table}_{timestamp}.csv"
            df.to_csv(csv_file, index=False)
            print(f"Exported {table} to {csv_file}")

    # ==================== STATISTICS / ANALYTICS ====================

    def get_player_averages(self, player_name: str, num_weeks: int = 4) -> Dict[str, float]:
        """
        Calculate player's recent averages.

        Args:
            player_name: Player name
            num_weeks: Number of recent weeks to average

        Returns:
            Dictionary of stat averages
        """
        df = self.get_player_history(player_name, num_weeks)

        if df.empty:
            return {}

        averages = {
            "avg_points": df["actual_points"].mean(),
            "avg_passing_yards": df["passing_yards"].mean(),
            "avg_passing_tds": df["passing_tds"].mean(),
            "avg_rushing_yards": df["rushing_yards"].mean(),
            "avg_rushing_tds": df["rushing_tds"].mean(),
            "avg_receiving_yards": df["receiving_yards"].mean(),
            "avg_receiving_tds": df["receiving_tds"].mean(),
            "avg_receptions": df["receptions"].mean(),
            "consistency": df["actual_points"].std(),  # Lower = more consistent
            "games_played": len(df),
        }

        return averages

    # ==================== PLAY-BY-PLAY METHODS ====================

    def run_migration(self, migration_file: str):
        """
        Run a specific migration file.

        Args:
            migration_file: Name of migration file (e.g., '002_play_by_play_schema.sql')
        """
        migration_path = Path(__file__).parent / "migrations" / migration_file

        if not migration_path.exists():
            raise FileNotFoundError(f"Migration file not found: {migration_path}")

        with open(migration_path, "r") as f:
            migration_sql = f.read()

        self.conn.executescript(migration_sql)
        self.conn.commit()

    def store_games(self, games_df: pd.DataFrame, show_progress: bool = False) -> int:
        """
        Store game metadata.

        Args:
            games_df: DataFrame with game data from nflverse
            show_progress: Whether to show progress bar (games are usually fast)

        Returns:
            Number of games stored
        """
        # Select only columns that exist in our schema
        game_columns = [
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

        # Filter to only existing columns
        available_cols = [col for col in game_columns if col in games_df.columns]
        games_subset = games_df[available_cols].copy()

        # Mark games as finished if we have final scores
        if "home_score" in games_subset.columns and "away_score" in games_subset.columns:
            games_subset["game_finished"] = games_subset["home_score"].notna().astype(int)

        # Insert or replace games (games are small, no batching needed)
        games_subset.to_sql("games", self.conn, if_exists="append", index=False)
        self.conn.commit()

        return len(games_subset)

    def store_plays(self, plays_df: pd.DataFrame, show_progress: bool = True) -> int:
        """
        Store play-by-play data with batched inserts for better performance.

        Args:
            plays_df: DataFrame with play data from nflverse
            show_progress: Whether to show progress bar

        Returns:
            Number of plays stored
        """
        from tqdm import tqdm

        # Get list of columns in our schema
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(plays)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        # Filter to only columns that exist in schema (exclude created_at)
        available_cols = [col for col in plays_df.columns if col in schema_columns and col != "created_at"]

        plays_subset = plays_df[available_cols].copy()

        # Batch insert for better performance
        batch_size = 1000
        total_rows = len(plays_subset)
        inserted = 0

        # Optimize SQLite for bulk insert
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")

        pbar = tqdm(total=total_rows, desc="Storing plays", disable=not show_progress, unit=" plays")

        skipped_duplicates = 0

        try:
            for start_idx in range(0, total_rows, batch_size):
                end_idx = min(start_idx + batch_size, total_rows)
                batch = plays_subset.iloc[start_idx:end_idx]

                try:
                    batch.to_sql("plays", self.conn, if_exists="append", index=False, method="multi")
                    batch_inserted = len(batch)
                    inserted += batch_inserted
                    pbar.update(batch_inserted)
                except Exception as e:
                    # If batch fails (likely duplicates), try row by row
                    batch_skipped = 0
                    for _, row in batch.iterrows():
                        try:
                            row_df = row.to_frame().T
                            row_df.to_sql("plays", self.conn, if_exists="append", index=False)
                            inserted += 1
                        except Exception:
                            # Skip duplicates (UNIQUE constraint) or other errors
                            batch_skipped += 1
                        pbar.update(1)
                    skipped_duplicates += batch_skipped

            self.conn.commit()

            if skipped_duplicates > 0 and show_progress:
                pbar.write(f"  [INFO] Skipped {skipped_duplicates} duplicate plays")

        finally:
            # Restore normal settings
            cursor.execute("PRAGMA synchronous = FULL")
            cursor.execute("PRAGMA journal_mode = DELETE")
            pbar.close()

        return inserted

    def store_ftn_charting(self, ftn_df: pd.DataFrame, show_progress: bool = True) -> int:
        """
        Store FTN charting data with batched inserts.

        Args:
            ftn_df: DataFrame with FTN charting data
            show_progress: Whether to show progress bar

        Returns:
            Number of records stored
        """
        from tqdm import tqdm

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(ftn_charting)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [col for col in ftn_df.columns if col in schema_columns and col != "created_at"]

        ftn_subset = ftn_df[available_cols].copy()

        # Filter out rows with null required fields (play_id is required)
        if "play_id" in ftn_subset.columns:
            initial_count = len(ftn_subset)
            ftn_subset = ftn_subset[ftn_subset["play_id"].notna()].copy()
            filtered_count = initial_count - len(ftn_subset)
            if filtered_count > 0 and show_progress:
                print(f"  [INFO] Filtered out {filtered_count} FTN records with NULL play_id")

        if len(ftn_subset) == 0:
            if show_progress:
                print("  [WARN] No valid FTN records to store after filtering")
            return 0

        # Batch insert for larger datasets
        batch_size = 1000
        total_rows = len(ftn_subset)
        inserted = 0

        pbar = tqdm(total=total_rows, desc="Storing FTN data", disable=not show_progress, unit=" records")

        try:
            for start_idx in range(0, total_rows, batch_size):
                end_idx = min(start_idx + batch_size, total_rows)
                batch = ftn_subset.iloc[start_idx:end_idx]

                try:
                    batch.to_sql("ftn_charting", self.conn, if_exists="append", index=False)
                    batch_inserted = len(batch)
                    inserted += batch_inserted
                    pbar.update(batch_inserted)
                except:
                    # Skip duplicates
                    for _, row in batch.iterrows():
                        try:
                            row_df = row.to_frame().T
                            row_df.to_sql("ftn_charting", self.conn, if_exists="append", index=False)
                            inserted += 1
                        except:
                            pass
                        pbar.update(1)

            self.conn.commit()

        finally:
            pbar.close()

        return inserted

    def store_snap_counts(self, snaps_df: pd.DataFrame, show_progress: bool = True) -> int:
        """
        Store snap count data with batched inserts.

        Args:
            snaps_df: DataFrame with snap count data
            show_progress: Whether to show progress bar

        Returns:
            Number of records stored
        """
        from tqdm import tqdm

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(snap_counts)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [col for col in snaps_df.columns if col in schema_columns and col != "created_at"]

        snaps_subset = snaps_df[available_cols].copy()

        # Filter out rows with null required fields
        initial_count = len(snaps_subset)
        if "player_id" in snaps_subset.columns:
            snaps_subset = snaps_subset[snaps_subset["player_id"].notna()].copy()
        if "game_id" in snaps_subset.columns:
            snaps_subset = snaps_subset[snaps_subset["game_id"].notna()].copy()

        filtered_count = initial_count - len(snaps_subset)
        if filtered_count > 0 and show_progress:
            print(f"  [INFO] Filtered out {filtered_count} snap count records with NULL required fields")

        if len(snaps_subset) == 0:
            if show_progress:
                print("  [WARN] No valid snap count records to store after filtering")
            return 0

        # Batch insert for larger datasets
        batch_size = 1000
        total_rows = len(snaps_subset)
        inserted = 0

        pbar = tqdm(total=total_rows, desc="Storing snap counts", disable=not show_progress, unit=" records")

        try:
            for start_idx in range(0, total_rows, batch_size):
                end_idx = min(start_idx + batch_size, total_rows)
                batch = snaps_subset.iloc[start_idx:end_idx]

                try:
                    batch.to_sql("snap_counts", self.conn, if_exists="append", index=False)
                    batch_inserted = len(batch)
                    inserted += batch_inserted
                    pbar.update(batch_inserted)
                except:
                    # Skip duplicates
                    for _, row in batch.iterrows():
                        try:
                            row_df = row.to_frame().T
                            row_df.to_sql("snap_counts", self.conn, if_exists="append", index=False)
                            inserted += 1
                        except:
                            pass
                        pbar.update(1)

            self.conn.commit()

        finally:
            pbar.close()

        return inserted

    def log_data_load(
        self, load_type: str, season: int, week: Optional[int] = None, status: str = "started"
    ) -> int:
        """
        Log a data load operation.

        Args:
            load_type: Type of load (pbp, ftn, snaps, roster)
            season: Season year
            week: Optional week number
            status: Load status (started, completed, failed)

        Returns:
            load_id for tracking
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """INSERT INTO data_loads (load_type, season, week, status)
               VALUES (?, ?, ?, ?)""",
            (load_type, season, week, status),
        )

        self.conn.commit()
        return cursor.lastrowid

    def update_data_load(
        self, load_id: int, status: str, records_loaded: int = 0, error: Optional[str] = None
    ):
        """
        Update data load status.

        Args:
            load_id: ID from log_data_load
            status: New status (completed, failed)
            records_loaded: Number of records loaded
            error: Optional error message
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """UPDATE data_loads
               SET status = ?,
                   records_loaded = ?,
                   error_message = ?,
                   completed_at = CURRENT_TIMESTAMP,
                   duration_seconds = (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400
               WHERE load_id = ?""",
            (status, records_loaded, error, load_id),
        )

        self.conn.commit()

    def get_latest_game_id(self, season: int) -> Optional[str]:
        """
        Get the most recent game_id for incremental updates.

        Args:
            season: Season year

        Returns:
            Latest game_id or None
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT game_id
               FROM games
               WHERE season = ?
               ORDER BY game_date DESC, game_id DESC
               LIMIT 1""",
            (season,),
        )

        row = cursor.fetchone()
        return row[0] if row else None

    def get_plays(
        self,
        season: int,
        week: Optional[int] = None,
        team: Optional[str] = None,
        play_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Query play-by-play data with flexible filters.

        Args:
            season: Season year
            week: Optional week filter
            team: Optional team filter (posteam or defteam)
            play_type: Optional play type filter (pass, run, etc.)
            limit: Optional limit on results

        Returns:
            DataFrame with play data
        """
        query = "SELECT * FROM plays WHERE season = ?"
        params = [season]

        if week is not None:
            query += " AND week = ?"
            params.append(week)

        if team:
            query += " AND (posteam = ? OR defteam = ?)"
            params.extend([team, team])

        if play_type:
            query += " AND play_type = ?"
            params.append(play_type)

        query += " ORDER BY game_id, play_id"

        if limit:
            query += f" LIMIT {limit}"

        return pd.read_sql(query, self.conn, params=params)

    def get_player_plays(
        self, player_name: str, season: int, play_types: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get all plays involving a specific player.

        Args:
            player_name: Player name
            season: Season year
            play_types: Optional list of play types to filter

        Returns:
            DataFrame with player's plays
        """
        query = """
            SELECT *
            FROM plays
            WHERE (passer_player_name = ? OR rusher_player_name = ? OR receiver_player_name = ?)
                AND season = ?
        """
        params = [player_name, player_name, player_name, season]

        if play_types:
            placeholders = ",".join("?" * len(play_types))
            query += f" AND play_type IN ({placeholders})"
            params.extend(play_types)

        query += " ORDER BY game_date, play_id"

        return pd.read_sql(query, self.conn, params=params)

    def get_player_targets(
        self, player_name: str, season: int, weeks: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get all targets for a receiver.

        Args:
            player_name: Receiver name
            season: Season year
            weeks: Optional list of weeks to filter

        Returns:
            DataFrame with target data
        """
        query = """
            SELECT
                game_id, week, game_date,
                complete_pass, air_yards, yards_gained,
                touchdown, epa, wpa, cpoe
            FROM plays
            WHERE receiver_player_name = ?
                AND season = ?
                AND play_type = 'pass'
        """
        params = [player_name, season]

        if weeks:
            placeholders = ",".join("?" * len(weeks))
            query += f" AND week IN ({placeholders})"
            params.extend(weeks)

        query += " ORDER BY game_date, play_id"

        return pd.read_sql(query, self.conn, params=params)

    def calculate_target_share(self, player_name: str, season: int, week: Optional[int] = None) -> float:
        """
        Calculate player's target share for their team.

        Args:
            player_name: Receiver name
            season: Season year
            week: Optional week filter (None for full season)

        Returns:
            Target share as decimal (e.g., 0.25 = 25%)
        """
        # Get player's team
        player_query = """
            SELECT DISTINCT posteam
            FROM plays
            WHERE receiver_player_name = ?
                AND season = ?
            LIMIT 1
        """
        result = pd.read_sql(player_query, self.conn, params=[player_name, season])

        if result.empty:
            return 0.0

        team = result["posteam"].iloc[0]

        # Build query with optional week filter
        week_filter = "AND week = ?" if week else ""
        params_player = [player_name, season]
        params_team = [team, season]

        if week:
            params_player.append(week)
            params_team.append(week)

        # Calculate target share
        share_query = f"""
            WITH player_targets AS (
                SELECT COUNT(*) as player_count
                FROM plays
                WHERE receiver_player_name = ?
                    AND season = ?
                    AND play_type = 'pass'
                    {week_filter}
            ),
            team_targets AS (
                SELECT COUNT(*) as team_count
                FROM plays
                WHERE posteam = ?
                    AND season = ?
                    AND play_type = 'pass'
                    {week_filter}
            )
            SELECT
                CAST(player_count AS FLOAT) / NULLIF(team_count, 0) as target_share
            FROM player_targets, team_targets
        """

        result = pd.read_sql(share_query, self.conn, params=params_player + params_team)

        if result.empty or result["target_share"].isna().all():
            return 0.0

        return float(result["target_share"].iloc[0])

    def get_red_zone_stats(self, player_name: str, season: int, red_zone_yards: int = 20) -> Dict[str, float]:
        """
        Get player's red zone statistics.

        Args:
            player_name: Player name
            season: Season year
            red_zone_yards: Yards from goal line (default 20)

        Returns:
            Dictionary of red zone stats
        """
        query = f"""
            SELECT
                COUNT(*) as plays,
                SUM(CASE WHEN rusher_player_name = ? THEN 1 ELSE 0 END) as rushes,
                SUM(CASE WHEN receiver_player_name = ? THEN 1 ELSE 0 END) as targets,
                SUM(CASE WHEN touchdown = 1 THEN 1 ELSE 0 END) as tds,
                AVG(epa) as avg_epa
            FROM plays
            WHERE (rusher_player_name = ? OR receiver_player_name = ?)
                AND yardline_100 <= ?
                AND season = ?
                AND play_type IN ('pass', 'run')
        """

        result = pd.read_sql(
            query,
            self.conn,
            params=[player_name, player_name, player_name, player_name, red_zone_yards, season],
        )

        if result.empty:
            return {}

        return {
            "red_zone_plays": int(result["plays"].iloc[0]),
            "red_zone_rushes": int(result["rushes"].iloc[0]),
            "red_zone_targets": int(result["targets"].iloc[0]),
            "red_zone_tds": int(result["tds"].iloc[0]),
            "red_zone_avg_epa": float(result["avg_epa"].iloc[0]) if result["avg_epa"].iloc[0] else 0.0,
        }

    def get_game_snap_share(self, player_name: str, season: int, week: Optional[int] = None) -> pd.DataFrame:
        """
        Get player's snap counts and percentages.

        Args:
            player_name: Player name
            season: Season year
            week: Optional week filter

        Returns:
            DataFrame with snap data
        """
        query = """
            SELECT
                game_id, week, team, opponent,
                offense_snaps, offense_pct,
                defense_snaps, defense_pct,
                st_snaps, st_pct
            FROM snap_counts
            WHERE player_name = ?
                AND season = ?
        """
        params = [player_name, season]

        if week:
            query += " AND week = ?"
            params.append(week)

        query += " ORDER BY week"

        return pd.read_sql(query, self.conn, params=params)

    # ==================== HISTORICAL GAMES (BACKTEST SUPPORT) ====================

    def get_historical_games(
        self,
        season: int,
        week: Optional[int] = None,
        season_type: str = "REG",
        finished_only: bool = True,
    ) -> pd.DataFrame:
        """Fetch completed games for backtesting pick'em strategies.

        Returns one row per game with pre-game market data (spread_line,
        total_line) and final scores. Only pulls finished games by default so
        that backtesters never accidentally see in-progress or unplayed weeks.

        Args:
            season: NFL season year.
            week: Optional week filter (None = whole season).
            season_type: 'REG', 'POST', or 'PRE'. Default 'REG'.
            finished_only: If True (default), exclude rows where either score is NULL.

        Returns:
            DataFrame with: game_id, season, season_type, week, game_date,
            home_team, away_team, home_score, away_score, spread_line,
            total_line, roof, surface, temp, wind. Sorted by week, game_date.
        """
        query = """
            SELECT game_id, season, season_type, week, game_date,
                   home_team, away_team, home_score, away_score,
                   spread_line, total_line,
                   roof, surface, temp, wind
            FROM games
            WHERE season = ? AND season_type = ?
        """
        params: List = [season, season_type]

        if week is not None:
            query += " AND week = ?"
            params.append(week)

        if finished_only:
            query += " AND home_score IS NOT NULL AND away_score IS NOT NULL"

        query += " ORDER BY week, game_date, game_id"
        return pd.read_sql(query, self.conn, params=params)

    def get_data_coverage(
        self,
        season_start: Optional[int] = None,
        season_end: Optional[int] = None,
        season_type: str = "REG",
    ) -> pd.DataFrame:
        """Audit historical game-data completeness per (season, week).

        A (season, week) window is "fully_usable" for backtesting only when every
        game in that window has both a final score and a spread_line. Backtesters
        should refuse to run over non-fully-usable windows unless explicitly
        opted in.

        Args:
            season_start: Inclusive lower bound (None = no bound).
            season_end:   Inclusive upper bound (None = no bound).
            season_type: 'REG', 'POST', or 'PRE'. Default 'REG'.

        Returns:
            DataFrame with: season, week, n_games, with_spread, with_total,
            with_scores, pct_with_spread, fully_usable (1/0). Sorted by
            season, week.
        """
        clauses = ["season_type = ?"]
        params: List = [season_type]

        if season_start is not None:
            clauses.append("season >= ?")
            params.append(season_start)
        if season_end is not None:
            clauses.append("season <= ?")
            params.append(season_end)

        where_sql = " AND ".join(clauses)
        query = f"""
            SELECT
                season,
                week,
                COUNT(*) AS n_games,
                SUM(CASE WHEN spread_line IS NOT NULL THEN 1 ELSE 0 END) AS with_spread,
                SUM(CASE WHEN total_line  IS NOT NULL THEN 1 ELSE 0 END) AS with_total,
                SUM(CASE WHEN home_score IS NOT NULL
                          AND away_score IS NOT NULL THEN 1 ELSE 0 END) AS with_scores
            FROM games
            WHERE {where_sql}
            GROUP BY season, week
            ORDER BY season, week
        """
        df = pd.read_sql(query, self.conn, params=params)

        if df.empty:
            return df

        df["pct_with_spread"] = (100.0 * df["with_spread"] / df["n_games"]).round(1)
        df["fully_usable"] = (
            (df["with_spread"] == df["n_games"]) & (df["with_scores"] == df["n_games"])
        ).astype(int)
        return df
