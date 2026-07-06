"""Database operations for FFPy - Focus on historical actual stats."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _sqlite_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sqlite_records(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [tuple(_sqlite_value(value) for value in row) for row in df.itertuples(index=False, name=None)]


def _insert_or_ignore_dataframe(
    conn: sqlite3.Connection,
    table: str,
    df: pd.DataFrame,
    columns: list[str],
) -> int:
    if df.empty:
        return 0

    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor = conn.cursor()
    try:
        cursor.executemany(
            f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[columns]),
        )
        return max(cursor.rowcount, 0)
    finally:
        cursor.close()


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

        # Connect to database (check_same_thread=False for FastAPI/uvicorn thread safety)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
        self.conn.execute("PRAGMA foreign_keys = ON")  # enable ON DELETE CASCADE

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
        for name in (
            "001_initial_schema.sql",
            "003_backtest_schema.sql",
            "004_advanced_stats.sql",
            "005_ngs.sql",
            "006_injuries.sql",
            "007_dfs.sql",
            "008_adp.sql",
            "009_depth_charts.sql",
            "010_quality_views.sql",
            "011_game_weather.sql",
            "012_player_rosters.sql",
            "013_offensive_line_stats.sql",
            "014_league_import.sql",
            "015_cfb_schema.sql",
            "016_cfb_fantasy_schema.sql",
            "017_cfb_transactions.sql",
            "018_cfb_league_settings.sql",
            "019_cfb_draft.sql",
            "020_cfb_waivers.sql",
            "021_cfb_trades.sql",
            "022_cfb_adp.sql",
        ):
            with open(migrations_dir / name, "r") as f:
                self.conn.executescript(f.read())
        self._upgrade_cfb_columns()
        self.conn.commit()

    def _upgrade_cfb_columns(self) -> None:
        """Idempotent column adds for CFB tables upgraded from 015."""
        alters = [
            "ALTER TABLE cfb_rosters ADD COLUMN position_id TEXT",
            "ALTER TABLE cfb_rosters ADD COLUMN position TEXT",
            "ALTER TABLE cfb_rosters ADD COLUMN cfbd_athlete_id INTEGER",
            "ALTER TABLE cfb_player_game_stats ADD COLUMN full_name TEXT",
            "ALTER TABLE cfb_transactions ADD COLUMN drop_player_id INTEGER",
            "ALTER TABLE cfb_transactions ADD COLUMN priority INTEGER DEFAULT 0",
            "ALTER TABLE cfb_transactions ADD COLUMN week INTEGER",
            "ALTER TABLE cfb_transactions ADD COLUMN processed_at TIMESTAMP",
            "ALTER TABLE cfb_transactions ADD COLUMN failure_reason TEXT",
        ]
        for stmt in alters:
            try:
                self.conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

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
        tables = [
            "players",
            "actual_stats",
            "projections",
            "api_requests",
            "player_advanced_stats",
            "nextgen_stats",
            "player_injuries",
            "dfs_salaries",
            "adp",
            "depth_charts",
            "player_rosters",
            "game_weather",
        ]

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

        if games_subset.empty:
            return 0

        # Insert or replace games (games are small, no batching needed).
        columns = list(games_subset.columns)
        column_sql = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        cursor = self.conn.cursor()
        cursor.executemany(
            f"INSERT OR REPLACE INTO games ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(games_subset),
        )
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
        cursor.fetchone()

        pbar = tqdm(total=total_rows, desc="Storing plays", disable=not show_progress, unit=" plays")

        skipped_duplicates = 0

        try:
            for start_idx in range(0, total_rows, batch_size):
                end_idx = min(start_idx + batch_size, total_rows)
                batch = plays_subset.iloc[start_idx:end_idx]

                batch_inserted = _insert_or_ignore_dataframe(self.conn, "plays", batch, available_cols)
                inserted += batch_inserted
                skipped_duplicates += len(batch) - batch_inserted
                pbar.update(len(batch))

            self.conn.commit()

            if skipped_duplicates > 0 and show_progress:
                pbar.write(f"  [INFO] Skipped {skipped_duplicates} duplicate plays")

        finally:
            # Restore normal settings
            cursor.execute("PRAGMA synchronous = FULL")
            cursor.execute("PRAGMA journal_mode = DELETE")
            cursor.fetchone()
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
                    batch_inserted = _insert_or_ignore_dataframe(
                        self.conn, "ftn_charting", batch, available_cols
                    )
                    inserted += batch_inserted
                    pbar.update(len(batch))
                except Exception:
                    raise

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
                    batch_inserted = _insert_or_ignore_dataframe(
                        self.conn, "snap_counts", batch, available_cols
                    )
                    inserted += batch_inserted
                    pbar.update(len(batch))
                except Exception:
                    raise

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
        query = """
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

    # ==================== ADVANCED PLAYER STATS (Phase 1) ====================

    def store_player_advanced_stats(self, df: pd.DataFrame, season: int) -> int:
        """
        Store or replace derived advanced player stats.

        Args:
            df: DataFrame with columns matching player_advanced_stats schema
            season: Season year (for data_load tracking)

        Returns:
            Number of rows stored
        """
        from tqdm import tqdm

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(player_advanced_stats)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("stat_id", "created_at")
        ]
        if not available_cols:
            return 0

        batch_size = 500
        total_rows = len(df)
        inserted = 0
        pbar = tqdm(total=total_rows, desc="Storing advanced stats", unit=" rows")

        try:
            for start_idx in range(0, total_rows, batch_size):
                end_idx = min(start_idx + batch_size, total_rows)
                batch = df.iloc[start_idx:end_idx]
                column_sql = ", ".join(available_cols)
                placeholders = ", ".join("?" for _ in available_cols)
                cursor.executemany(
                    f"INSERT OR REPLACE INTO player_advanced_stats ({column_sql}) VALUES ({placeholders})",
                    _sqlite_records(batch[available_cols]),
                )
                inserted += max(cursor.rowcount, 0)
                pbar.update(len(batch))

            self.conn.commit()
        finally:
            pbar.close()

        return inserted

    def get_player_advanced_stats(
        self,
        player_name: str,
        season: int,
        week: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Retrieve advanced stats for a player.

        Args:
            player_name: Player name
            season: Season year
            week: Optional week filter

        Returns:
            DataFrame with advanced stats
        """
        query = "SELECT * FROM player_advanced_stats WHERE player_name = ? AND season = ?"
        params: List = [player_name, season]
        if week is not None:
            query += " AND week = ?"
            params.append(week)
        query += " ORDER BY week"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== NEXT GEN STATS (Phase 2A) ====================

    def store_nextgen_stats(self, df: pd.DataFrame, season: int) -> int:
        """
        Store or replace Next Gen Stats data.

        Args:
            df: DataFrame with normalized NGS columns
            season: Season year

        Returns:
            Number of rows stored
        """
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(nextgen_stats)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("ngs_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        cursor.executemany(
            f"INSERT OR REPLACE INTO nextgen_stats ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_nextgen_stats(
        self,
        player_name: Optional[str] = None,
        season: Optional[int] = None,
        week: Optional[int] = None,
        position: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retrieve Next Gen Stats.

        Args:
            player_name: Optional player filter
            season: Optional season filter
            week: Optional week filter
            position: Optional position filter

        Returns:
            DataFrame with NGS data
        """
        conditions: List[str] = []
        params: List = []
        if player_name is not None:
            conditions.append("player_name = ?")
            params.append(player_name)
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if week is not None:
            conditions.append("week = ?")
            params.append(week)
        if position is not None:
            conditions.append("position = ?")
            params.append(position)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM nextgen_stats WHERE {where_sql} ORDER BY season, week"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== INJURIES (Phase 2B) ====================

    def store_player_injuries(self, df: pd.DataFrame, season: int) -> int:
        """
        Store or replace player injury data.

        Args:
            df: DataFrame with normalized injury columns
            season: Season year

        Returns:
            Number of rows stored
        """
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(player_injuries)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("injury_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        cursor.executemany(
            f"INSERT OR REPLACE INTO player_injuries ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_player_injuries(
        self,
        player_name: Optional[str] = None,
        season: Optional[int] = None,
        week: Optional[int] = None,
        game_status: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retrieve player injury data.

        Args:
            player_name: Optional player filter
            season: Optional season filter
            week: Optional week filter
            game_status: Optional game status filter (Active, Questionable, Out, etc.)

        Returns:
            DataFrame with injury data
        """
        conditions: List[str] = []
        params: List = []
        if player_name is not None:
            conditions.append("player_name = ?")
            params.append(player_name)
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if week is not None:
            conditions.append("week = ?")
            params.append(week)
        if game_status is not None:
            conditions.append("game_status = ?")
            params.append(game_status)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM player_injuries WHERE {where_sql} ORDER BY season, week"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== DFS SALARIES (Phase 3A) ====================

    def store_dfs_salaries(self, df: pd.DataFrame, season: int, week: int, platform: str) -> int:
        """
        Store DFS salary data.

        Args:
            df: DataFrame with columns: player_name, salary, position, team, opponent
            season: Season year
            week: Week number
            platform: Platform name (draftkings, fanduel)

        Returns:
            Number of rows stored
        """
        df = df.copy()
        df["season"] = season
        df["week"] = week
        df["platform"] = platform

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(dfs_salaries)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("dfs_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        cursor.executemany(
            f"INSERT OR REPLACE INTO dfs_salaries ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_dfs_salaries(
        self,
        season: int,
        week: int,
        platform: Optional[str] = None,
        position: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retrieve DFS salaries.

        Args:
            season: Season year
            week: Week number
            platform: Optional platform filter
            position: Optional position filter

        Returns:
            DataFrame with DFS salary data
        """
        query = "SELECT * FROM dfs_salaries WHERE season = ? AND week = ?"
        params: List = [season, week]
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        if position:
            query += " AND position = ?"
            params.append(position)
        query += " ORDER BY salary DESC"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== ADP (Phase 3B) ====================

    def store_adp(self, df: pd.DataFrame, season: int) -> int:
        """
        Store ADP data.

        Args:
            df: DataFrame with columns: player_name, position, platform, adp, adp_high, adp_low, draft_date
            season: Season year

        Returns:
            Number of rows stored
        """
        df = df.copy()
        df["season"] = season

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(adp)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("adp_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        cursor.executemany(
            f"INSERT OR REPLACE INTO adp ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_adp(
        self,
        position: Optional[str] = None,
        platform: Optional[str] = None,
        season: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Retrieve ADP data.

        Args:
            position: Optional position filter
            platform: Optional platform filter
            season: Optional season filter
            top_n: Optional limit to top N players by ADP

        Returns:
            DataFrame with ADP data
        """
        conditions: List[str] = []
        params: List = []
        if position is not None:
            conditions.append("position = ?")
            params.append(position)
        if platform is not None:
            conditions.append("platform = ?")
            params.append(platform)
        if season is not None:
            conditions.append("season = ?")
            params.append(season)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM adp WHERE {where_sql} ORDER BY adp ASC"
        if top_n:
            query += f" LIMIT {top_n}"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== DEPTH CHARTS (Phase 3C) ====================

    def store_depth_charts(self, df: pd.DataFrame, season: int) -> int:
        """
        Store depth chart data.

        Args:
            df: DataFrame with columns: team, season, week, position, player_name, depth_spot
            season: Season year

        Returns:
            Number of rows stored
        """
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(depth_charts)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("dc_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        cursor.executemany(
            f"INSERT OR REPLACE INTO depth_charts ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_depth_charts(
        self,
        team: Optional[str] = None,
        season: Optional[int] = None,
        week: Optional[int] = None,
        position: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retrieve depth chart data.

        Args:
            team: Optional team filter
            season: Optional season filter
            week: Optional week filter
            position: Optional position filter

        Returns:
            DataFrame with depth chart data
        """
        conditions: List[str] = []
        params: List = []
        if team is not None:
            conditions.append("team = ?")
            params.append(team)
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if week is not None:
            conditions.append("week = ?")
            params.append(week)
        if position is not None:
            conditions.append("position = ?")
            params.append(position)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM depth_charts WHERE {where_sql} ORDER BY team, position, depth_spot"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== PLAYER ROSTERS (Phase 1) ====================

    def store_player_rosters(self, df: pd.DataFrame, season: int) -> int:
        """
        Store or replace seasonal player roster data.

        Args:
            df: DataFrame with columns matching player_rosters schema
            season: Season year

        Returns:
            Number of rows stored
        """
        df = df.copy()
        df = df.dropna(subset=["gsis_id"])
        if df.empty:
            return 0

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(player_rosters)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("roster_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        update_sql = ", ".join(
            f"{col}=excluded.{col}" for col in available_cols if col not in ("gsis_id", "season")
        )
        cursor.executemany(
            f"""INSERT INTO player_rosters ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(gsis_id, season) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_player_rosters(
        self,
        season: Optional[int] = None,
        player_name: Optional[str] = None,
        position: Optional[str] = None,
        team: Optional[str] = None,
        gsis_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retrieve player roster data.

        Args:
            season: Optional season filter
            player_name: Optional player name filter
            position: Optional position filter
            team: Optional team filter
            gsis_id: Optional GSIS ID filter

        Returns:
            DataFrame with roster data
        """
        conditions: list[str] = []
        params: list = []
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if player_name is not None:
            conditions.append("player_name = ?")
            params.append(player_name)
        if position is not None:
            conditions.append("position = ?")
            params.append(position)
        if team is not None:
            conditions.append("team = ?")
            params.append(team)
        if gsis_id is not None:
            conditions.append("gsis_id = ?")
            params.append(gsis_id)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM player_rosters WHERE {where_sql} ORDER BY player_name"
        return pd.read_sql(query, self.conn, params=params)

    def get_rookie_draft_capital(self, player_name: str, season: int) -> Optional[Dict[str, int]]:
        """
        Get a player's draft capital (round, pick) from their rookie season.

        Uses the earliest season available in player_rosters for the player.

        Args:
            player_name: Player name
            season: Current season (used to find earliest roster entry)

        Returns:
            Dict with draft_round and draft_pick, or None if unknown
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT draft_round, draft_pick
               FROM player_rosters
               WHERE player_name = ?
                 AND draft_round IS NOT NULL
               ORDER BY season ASC
               LIMIT 1""",
            (player_name,),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return {"draft_round": int(row[0]), "draft_pick": int(row[1]) if row[1] is not None else 999}
        return None

    def is_rookie(self, player_name: str, season: int) -> bool:
        """
        Check if a player is a rookie (years_exp == 0 or 1 in their first season).

        Args:
            player_name: Player name
            season: Current season

        Returns:
            True if the player is in their rookie season
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT years_exp
               FROM player_rosters
               WHERE player_name = ? AND season = ?
               LIMIT 1""",
            (player_name, season),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0]) <= 1
        # Fall back to checking if the player's earliest roster entry is this season
        cursor.execute(
            """SELECT MIN(season) FROM player_rosters WHERE player_name = ?""",
            (player_name,),
        )
        min_season = cursor.fetchone()
        return min_season is not None and min_season[0] is not None and min_season[0] == season

    # ==================== COLLEGE FOOTBALL (CFB) ====================

    def store_cfb_games(self, games_df: pd.DataFrame) -> int:
        """Store or replace college football game metadata."""
        if games_df.empty:
            return 0

        game_columns = [
            "game_id",
            "season",
            "week",
            "season_type",
            "game_date",
            "neutral_site",
            "conference_game",
            "home_id",
            "away_id",
            "home_team",
            "away_team",
            "home_abbreviation",
            "away_abbreviation",
            "home_score",
            "away_score",
            "home_winner",
            "away_winner",
            "venue",
            "attendance",
            "status",
            "game_finished",
            "source",
        ]
        available_cols = [col for col in game_columns if col in games_df.columns]
        subset = games_df[available_cols].copy()
        subset["game_id"] = subset["game_id"].astype(str)

        if (
            "home_score" in subset.columns
            and "away_score" in subset.columns
            and "game_finished" not in subset.columns
        ):
            subset["game_finished"] = (subset["home_score"].notna() & subset["away_score"].notna()).astype(
                int
            )

        columns = list(subset.columns)
        column_sql = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        cursor = self.conn.cursor()
        cursor.executemany(
            f"INSERT OR REPLACE INTO cfb_games ({column_sql}) VALUES ({placeholders})",
            _sqlite_records(subset),
        )
        self.conn.commit()
        return len(subset)

    def get_cfb_games(
        self,
        season: int,
        week: Optional[int] = None,
        season_type: Optional[int] = None,
        finished_only: bool = True,
    ) -> pd.DataFrame:
        """Fetch college football games for a season/week."""
        query = """
            SELECT game_id, season, week, season_type, game_date,
                   home_team, away_team, home_abbreviation, away_abbreviation,
                   home_score, away_score, venue, status, game_finished, source
            FROM cfb_games
            WHERE season = ?
        """
        params: List = [season]

        if week is not None:
            query += " AND week = ?"
            params.append(week)
        if season_type is not None:
            query += " AND season_type = ?"
            params.append(season_type)
        if finished_only:
            query += " AND home_score IS NOT NULL AND away_score IS NOT NULL"

        query += " ORDER BY week, game_date, game_id"
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_rosters(self, df: pd.DataFrame, season: int) -> int:
        """Store or update college football roster rows for a season."""
        df = df.copy()
        df["season"] = season
        df = df.dropna(subset=["athlete_id", "full_name"])
        if df.empty:
            return 0

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(cfb_rosters)")
        schema_columns = {row[1] for row in cursor.fetchall()}
        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("roster_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        update_sql = ", ".join(
            f"{col}=excluded.{col}"
            for col in available_cols
            if col not in ("season", "athlete_id", "team_id")
        )
        cursor.executemany(
            f"""INSERT INTO cfb_rosters ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(season, athlete_id, team_id) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_cfb_rosters(
        self,
        season: Optional[int] = None,
        team_abbreviation: Optional[str] = None,
        full_name: Optional[str] = None,
        athlete_id: Optional[int] = None,
    ) -> pd.DataFrame:
        """Retrieve college football roster data."""
        conditions: list[str] = []
        params: list = []
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if team_abbreviation is not None:
            conditions.append("team_abbreviation = ?")
            params.append(team_abbreviation)
        if full_name is not None:
            conditions.append("full_name = ?")
            params.append(full_name)
        if athlete_id is not None:
            conditions.append("athlete_id = ?")
            params.append(athlete_id)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM cfb_rosters WHERE {where_sql} ORDER BY team_abbreviation, full_name"
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_plays(self, plays_df: pd.DataFrame, show_progress: bool = True) -> int:
        """Store curated college football play-by-play rows."""
        from tqdm import tqdm

        if plays_df.empty:
            return 0

        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(cfb_plays)")
        schema_columns = {row[1] for row in cursor.fetchall()}
        available_cols = [col for col in plays_df.columns if col in schema_columns and col != "created_at"]
        subset = plays_df[available_cols].copy()

        batch_size = 1000
        total_rows = len(subset)
        inserted = 0

        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")
        cursor.fetchone()

        pbar = tqdm(total=total_rows, desc="Storing CFB plays", disable=not show_progress, unit=" plays")
        try:
            for start_idx in range(0, total_rows, batch_size):
                batch = subset.iloc[start_idx : start_idx + batch_size]
                inserted += _insert_or_ignore_dataframe(self.conn, "cfb_plays", batch, available_cols)
                pbar.update(len(batch))
            self.conn.commit()
        finally:
            cursor.execute("PRAGMA synchronous = FULL")
            cursor.execute("PRAGMA journal_mode = DELETE")
            cursor.fetchone()
            pbar.close()

        return inserted

    def get_cfb_plays(
        self,
        season: int,
        week: Optional[int] = None,
        team: Optional[str] = None,
        player_name: Optional[str] = None,
        play_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Query college football play-by-play data."""
        conditions = ["season = ?"]
        params: list = [season]

        if week is not None:
            conditions.append("week = ?")
            params.append(week)
        if team is not None:
            conditions.append("(pos_team = ? OR def_pos_team = ? OR home_team = ? OR away_team = ?)")
            params.extend([team, team, team, team])
        if player_name is not None:
            conditions.append(
                "(passer_player_name = ? OR rusher_player_name = ? OR receiver_player_name = ?)"
            )
            params.extend([player_name, player_name, player_name])
        if play_type is not None:
            conditions.append("play_type = ?")
            params.append(play_type)

        query = f"SELECT * FROM cfb_plays WHERE {' AND '.join(conditions)} ORDER BY game_id, play_id"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        return pd.read_sql(query, self.conn, params=params)

    def get_cfb_data_coverage(self) -> pd.DataFrame:
        """Summarize loaded CFB data by season."""
        query = """
            SELECT
                g.season,
                COUNT(DISTINCT g.game_id) AS n_games,
                COUNT(DISTINCT r.athlete_id) AS n_roster_players,
                (SELECT COUNT(*) FROM cfb_plays p WHERE p.season = g.season) AS n_plays
            FROM cfb_games g
            LEFT JOIN cfb_rosters r ON r.season = g.season
            GROUP BY g.season
            ORDER BY g.season
        """
        try:
            return pd.read_sql(query, self.conn)
        except Exception:
            return pd.DataFrame(columns=["season", "n_games", "n_roster_players", "n_plays"])

    # ==================== CFB FANTASY (Migration 016) ====================

    def store_cfb_teams(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = [
            "team_key",
            "season",
            "cfbd_team",
            "espn_team_id",
            "abbreviation",
            "school",
            "conference",
            "division",
            "classification",
            "color",
            "alt_color",
        ]
        available = [c for c in cols if c in df.columns]
        subset = df[available].drop_duplicates(subset=["team_key", "season"])
        column_sql = ", ".join(available)
        placeholders = ", ".join("?" for _ in available)
        update_sql = ", ".join(f"{c}=excluded.{c}" for c in available if c not in ("team_key", "season"))
        self.conn.executemany(
            f"""INSERT INTO cfb_teams ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(team_key, season) DO UPDATE SET {update_sql}""",
            _sqlite_records(subset),
        )
        self.conn.commit()
        return len(subset)

    def get_cfb_teams(self, season: int, conference: Optional[str] = None) -> pd.DataFrame:
        query = "SELECT * FROM cfb_teams WHERE season = ?"
        params: list = [season]
        if conference:
            query += " AND conference = ?"
            params.append(conference)
        query += " ORDER BY conference, school"
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_game_meta(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = [
            "game_id",
            "cfbd_game_id",
            "home_conference",
            "away_conference",
            "home_classification",
            "away_classification",
            "home_team_key",
            "away_team_key",
        ]
        available = [c for c in cols if c in df.columns]
        subset = df[available].copy()
        subset["game_id"] = subset["game_id"].astype(str)
        column_sql = ", ".join(available)
        placeholders = ", ".join("?" for _ in available)
        update_sql = ", ".join(f"{c}=excluded.{c}" for c in available if c != "game_id")
        self.conn.executemany(
            f"""INSERT INTO cfb_game_meta ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(game_id) DO UPDATE SET {update_sql}""",
            _sqlite_records(subset),
        )
        self.conn.commit()
        return len(subset)

    def get_cfb_game_meta(self, season: Optional[int] = None) -> pd.DataFrame:
        if season is None:
            return pd.read_sql("SELECT * FROM cfb_game_meta", self.conn)
        return pd.read_sql(
            """
            SELECT m.* FROM cfb_game_meta m
            JOIN cfb_games g ON m.game_id = g.game_id
            WHERE g.season = ?
            """,
            self.conn,
            params=[season],
        )

    def store_cfb_player_game_stats(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(cfb_player_game_stats)")
        schema_cols = {row[1] for row in cursor.fetchall()}
        cols = [c for c in df.columns if c in schema_cols and c != "stat_id"]
        if not cols:
            return 0
        update_cols = [c for c in cols if c not in ("cfbd_athlete_id", "cfbd_game_id", "category")]
        update_sql = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        column_sql = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        cursor.executemany(
            f"""INSERT INTO cfb_player_game_stats ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(cfbd_athlete_id, cfbd_game_id, category) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_cfb_player_game_stats(
        self, season: int, week: Optional[int] = None, team_key: Optional[str] = None
    ) -> pd.DataFrame:
        query = "SELECT * FROM cfb_player_game_stats WHERE season = ?"
        params: list = [season]
        if week is not None:
            query += " AND week = ?"
            params.append(week)
        if team_key:
            query += " AND team_key = ?"
            params.append(team_key)
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_team_defense_stats(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = [
            "team_key",
            "cfbd_game_id",
            "season",
            "week",
            "opponent_team_key",
            "sacks",
            "interceptions",
            "fumbles_recovered",
            "defensive_tds",
            "safeties",
            "points_allowed",
            "yards_allowed",
            "stat_json",
            "source",
        ]
        available = [c for c in cols if c in df.columns]
        column_sql = ", ".join(available)
        placeholders = ", ".join("?" for _ in available)
        update_sql = ", ".join(
            f"{c}=excluded.{c}" for c in available if c not in ("team_key", "cfbd_game_id")
        )
        self.conn.executemany(
            f"""INSERT INTO cfb_team_defense_stats ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(team_key, cfbd_game_id) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available]),
        )
        self.conn.commit()
        return len(df)

    def get_cfb_team_defense_stats(self, season: int, week: Optional[int] = None) -> pd.DataFrame:
        query = "SELECT * FROM cfb_team_defense_stats WHERE season = ?"
        params: list = [season]
        if week is not None:
            query += " AND week = ?"
            params.append(week)
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_players(self, df: pd.DataFrame, season: int) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df["season"] = season
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(cfb_players)")
        schema_cols = {row[1] for row in cursor.fetchall()}
        cols = [
            c for c in df.columns if c in schema_cols and c not in ("player_id", "created_at", "updated_at")
        ]
        stored = 0
        for _, row in df.iterrows():
            cfbd_id = row.get("cfbd_athlete_id")
            espn_id = row.get("espn_athlete_id")
            existing = None
            if pd.notna(cfbd_id):
                cursor.execute(
                    "SELECT player_id FROM cfb_players WHERE season = ? AND cfbd_athlete_id = ?",
                    (season, int(cfbd_id)),
                )
                existing = cursor.fetchone()
            if existing is None and pd.notna(espn_id):
                cursor.execute(
                    "SELECT player_id FROM cfb_players WHERE season = ? AND espn_athlete_id = ?",
                    (season, int(espn_id)),
                )
                existing = cursor.fetchone()
            values = [_sqlite_value(row[c]) for c in cols]
            if existing:
                set_sql = ", ".join(f"{c}=?" for c in cols)
                cursor.execute(
                    f"UPDATE cfb_players SET {set_sql}, updated_at = CURRENT_TIMESTAMP WHERE player_id = ?",
                    values + [existing[0]],
                )
            else:
                column_sql = ", ".join(cols)
                placeholders = ", ".join("?" for _ in cols)
                cursor.execute(
                    f"INSERT INTO cfb_players ({column_sql}) VALUES ({placeholders})",
                    values,
                )
            stored += 1
        self.conn.commit()
        return stored

    def get_cfb_players(
        self,
        season: int,
        conferences: Optional[List[str]] = None,
        position: Optional[str] = None,
        fantasy_eligible: Optional[bool] = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM cfb_players WHERE season = ?"
        params: list = [season]
        if conferences:
            placeholders = ", ".join("?" for _ in conferences)
            query += f" AND conference IN ({placeholders})"
            params.extend(conferences)
        if position:
            query += " AND position = ?"
            params.append(position)
        if fantasy_eligible is not None:
            query += " AND fantasy_eligible = ?"
            params.append(1 if fantasy_eligible else 0)
        query += " ORDER BY full_name"
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_id_map(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = [
            "season",
            "espn_athlete_id",
            "cfbd_athlete_id",
            "full_name",
            "team_key",
            "match_method",
            "confidence",
        ]
        available = [c for c in cols if c in df.columns]
        return _insert_or_ignore_dataframe(self.conn, "cfb_id_map", df, available)

    def store_cfb_fantasy_points(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(cfb_fantasy_points)")
        schema_cols = {row[1] for row in cursor.fetchall()}
        cols = [c for c in df.columns if c in schema_cols and c != "fp_id"]
        update_sql = ", ".join(
            f"{c}=excluded.{c}" for c in cols if c not in ("player_id", "season", "week", "scoring_preset")
        )
        column_sql = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        cursor.executemany(
            f"""INSERT INTO cfb_fantasy_points ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(player_id, season, week, scoring_preset) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[cols]),
        )
        self.conn.commit()
        return len(df)

    def get_cfb_fantasy_points(
        self,
        season: int,
        week: Optional[int] = None,
        max_week: Optional[int] = None,
        player_id: Optional[int] = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM cfb_fantasy_points WHERE season = ?"
        params: list = [season]
        if week is not None:
            query += " AND week = ?"
            params.append(week)
        if max_week is not None:
            query += " AND week <= ?"
            params.append(max_week)
        if player_id is not None:
            query += " AND player_id = ?"
            params.append(player_id)
        query += " ORDER BY week, actual_points DESC"
        return pd.read_sql(query, self.conn, params=params)

    def store_cfb_projections(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = [
            "player_id",
            "season",
            "week",
            "model",
            "projected_points",
            "passing_yards",
            "passing_tds",
            "interceptions",
            "rushing_yards",
            "rushing_tds",
            "receiving_yards",
            "receiving_tds",
            "receptions",
        ]
        available = [c for c in cols if c in df.columns]
        update_sql = ", ".join(
            f"{c}=excluded.{c}" for c in available if c not in ("player_id", "season", "week", "model")
        )
        column_sql = ", ".join(available)
        placeholders = ", ".join("?" for _ in available)
        self.conn.executemany(
            f"""INSERT INTO cfb_projections ({column_sql}) VALUES ({placeholders})
                ON CONFLICT(player_id, season, week, model) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available]),
        )
        self.conn.commit()
        return len(df)

    def get_cfb_projections(
        self, season: int, week: int, model: str = "historical", conferences: Optional[List[str]] = None
    ) -> pd.DataFrame:
        query = """
            SELECT p.*, pl.full_name, pl.position, pl.team_key, pl.conference
            FROM cfb_projections p
            JOIN cfb_players pl ON p.player_id = pl.player_id AND p.season = pl.season
            WHERE p.season = ? AND p.week = ? AND p.model = ?
        """
        params: list = [season, week, model]
        if conferences:
            placeholders = ", ".join("?" for _ in conferences)
            query += f" AND pl.conference IN ({placeholders})"
            params.extend(conferences)
        query += " ORDER BY p.projected_points DESC"
        return pd.read_sql(query, self.conn, params=params)

    def create_cfb_league(self, league: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_leagues (
                league_id, user_id, name, season, allowed_conferences,
                scoring_json, roster_slots_json, num_teams, playoff_weeks, fcs_discount_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league["league_id"],
                league["user_id"],
                league["name"],
                league["season"],
                league["allowed_conferences"],
                league["scoring_json"],
                league["roster_slots_json"],
                league.get("num_teams", 10),
                league.get("playoff_weeks"),
                league.get("fcs_discount_pct", 0.75),
            ),
        )
        self.conn.commit()
        self.seed_cfb_league_settings(league["league_id"])

    def get_cfb_league(self, league_id: str) -> Optional[dict]:
        cursor = self.conn.execute("SELECT * FROM cfb_leagues WHERE league_id = ?", (league_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_cfb_leagues(self, user_id: str) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM cfb_leagues WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def create_cfb_league_team(self, team: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_league_teams (league_team_id, league_id, team_name, owner_name, faab_budget)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                team["league_team_id"],
                team["league_id"],
                team["team_name"],
                team.get("owner_name"),
                team.get("faab_budget", 100),
            ),
        )
        self.conn.commit()

    def get_cfb_league_teams(self, league_id: str) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM cfb_league_teams WHERE league_id = ? ORDER BY team_name",
            (league_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def set_cfb_lineup(self, league_team_id: str, season: int, week: int, entries: list[dict]) -> None:
        self.conn.execute(
            "DELETE FROM cfb_lineups WHERE league_team_id = ? AND season = ? AND week = ?",
            (league_team_id, season, week),
        )
        for entry in entries:
            self.conn.execute(
                """
                INSERT INTO cfb_lineups (league_team_id, season, week, player_id, slot, is_starter)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    league_team_id,
                    season,
                    week,
                    entry["player_id"],
                    entry.get("slot", "FLEX"),
                    entry.get("is_starter", 1),
                ),
            )
        self.conn.commit()

    def get_cfb_lineup(self, league_team_id: str, season: int, week: int) -> pd.DataFrame:
        return pd.read_sql(
            """
            SELECT l.*, p.full_name, p.position, p.team_key
            FROM cfb_lineups l
            JOIN cfb_players p ON l.player_id = p.player_id AND l.season = p.season
            WHERE l.league_team_id = ? AND l.season = ? AND l.week = ?
            """,
            self.conn,
            params=[league_team_id, season, week],
        )

    def score_cfb_league_week(self, league_id: str, season: int, week: int) -> list[dict]:
        teams = self.get_cfb_league_teams(league_id)
        results = []
        for team in teams:
            lineup = self.get_cfb_lineup(team["league_team_id"], season, week)
            if lineup.empty:
                results.append({"league_team_id": team["league_team_id"], "points": 0.0, "starters": []})
                continue
            starters = lineup[lineup["is_starter"] == 1]
            total = 0.0
            starter_rows = []
            for _, slot in starters.iterrows():
                fp = self.get_cfb_fantasy_points(season=season, week=week, player_id=int(slot["player_id"]))
                pts = float(fp["actual_points"].iloc[0]) if not fp.empty else 0.0
                total += pts
                starter_rows.append(
                    {
                        "player_id": int(slot["player_id"]),
                        "full_name": slot["full_name"],
                        "position": slot["position"],
                        "points": pts,
                    }
                )
            results.append(
                {
                    "league_team_id": team["league_team_id"],
                    "team_name": team["team_name"],
                    "points": round(total, 2),
                    "starters": starter_rows,
                }
            )
        return results

    def get_cfb_league_roster(self, league_team_id: str) -> pd.DataFrame:
        return pd.read_sql(
            """
            SELECT r.*, p.full_name, p.position, p.team_key, p.conference
            FROM cfb_league_rosters r
            JOIN cfb_players p ON r.player_id = p.player_id
            WHERE r.league_team_id = ?
            ORDER BY r.slot, p.full_name
            """,
            self.conn,
            params=[league_team_id],
        )

    def get_cfb_league_rostered_player_ids(self, league_id: str) -> set[int]:
        cursor = self.conn.execute(
            """
            SELECT r.player_id
            FROM cfb_league_rosters r
            JOIN cfb_league_teams t ON r.league_team_id = t.league_team_id
            WHERE t.league_id = ?
            """,
            (league_id,),
        )
        return {int(row[0]) for row in cursor.fetchall()}

    def _cfb_max_roster_size(self, league: dict) -> int:
        import json

        from ffpy.optimizer import RosterConstraints

        slots = json.loads(league.get("roster_slots_json") or "{}")
        if slots:
            constraints = RosterConstraints.from_dict(slots)
            starters = constraints.total_starters or (
                sum(constraints.positions.values()) + constraints.num_flex
            )
            return int(starters) + 6
        return 15

    def validate_cfb_roster_move(self, league_id: str, player_id: int, action: str = "add") -> None:
        import json

        league = self.get_cfb_league(league_id)
        if not league:
            raise ValueError("League not found")
        if action != "add":
            return
        confs = json.loads(league.get("allowed_conferences") or "[]")
        season = int(league["season"])
        player = pd.read_sql(
            "SELECT * FROM vw_cfb_eligible_players WHERE player_id = ? AND season = ?",
            self.conn,
            params=[player_id, season],
        )
        if player.empty:
            raise ValueError("Player is not eligible for this league")
        if confs and player.iloc[0]["conference"] not in confs:
            raise ValueError("Player conference not allowed in this league")
        rostered = self.get_cfb_league_rostered_player_ids(league_id)
        if player_id in rostered:
            raise ValueError("Player is already rostered in this league")

    def add_cfb_roster_player(self, league_team_id: str, player_id: int, slot: str = "BENCH") -> None:
        team = self.conn.execute(
            "SELECT league_id FROM cfb_league_teams WHERE league_team_id = ?",
            (league_team_id,),
        ).fetchone()
        if not team:
            raise ValueError("Team not found")
        league_id = team[0]
        self.validate_cfb_roster_move(league_id, player_id, action="add")
        league = self.get_cfb_league(league_id)
        if league:
            roster = self.get_cfb_league_roster(league_team_id)
            if len(roster) >= self._cfb_max_roster_size(league):
                raise ValueError("Roster is full")
        self.conn.execute(
            """
            INSERT INTO cfb_league_rosters (league_team_id, player_id, slot)
            VALUES (?, ?, ?)
            ON CONFLICT(league_team_id, player_id) DO UPDATE SET slot = excluded.slot
            """,
            (league_team_id, player_id, slot),
        )
        self.conn.commit()

    def drop_cfb_roster_player(self, league_team_id: str, player_id: int) -> None:
        self.conn.execute(
            "DELETE FROM cfb_league_rosters WHERE league_team_id = ? AND player_id = ?",
            (league_team_id, player_id),
        )
        self.conn.commit()

    def get_cfb_standings(
        self, league_id: str, season: int, through_week: Optional[int] = None
    ) -> list[dict]:
        teams = self.get_cfb_league_teams(league_id)
        max_week = through_week or 16
        standings = []
        for team in teams:
            points_for = 0.0
            wins = int(team.get("wins") or 0)
            losses = int(team.get("losses") or 0)
            for week in range(1, max_week + 1):
                week_scores = self.score_cfb_league_week(league_id, season, week)
                for ws in week_scores:
                    if ws["league_team_id"] == team["league_team_id"]:
                        points_for += float(ws["points"])
            standings.append(
                {
                    "league_team_id": team["league_team_id"],
                    "team_name": team["team_name"],
                    "owner_name": team.get("owner_name"),
                    "wins": wins,
                    "losses": losses,
                    "points_for": round(points_for, 2),
                }
            )
        standings.sort(key=lambda x: (-x["points_for"], x["team_name"]))
        for i, row in enumerate(standings, start=1):
            row["rank"] = i
        return standings

    def generate_cfb_matchups(self, league_id: str, season: int, week: int) -> int:
        teams = self.get_cfb_league_teams(league_id)
        if len(teams) < 2:
            return 0
        team_ids = [t["league_team_id"] for t in teams]
        n = len(team_ids)
        if week < 1:
            return 0
        offset = (week - 1) % (n - 1) if n > 2 else 0
        rotated = [team_ids[0]] + team_ids[1 + offset :] + team_ids[1 : 1 + offset]
        if n % 2 == 1:
            rotated.append(None)
        pairs = []
        half = len(rotated) // 2
        for i in range(half):
            home = rotated[i]
            away = rotated[-(i + 1)]
            if home and away:
                pairs.append((home, away))
        self.conn.execute(
            """
            DELETE FROM cfb_matchups
            WHERE league_id = ? AND season = ? AND week = ?
            """,
            (league_id, season, week),
        )
        for home_id, away_id in pairs:
            self.conn.execute(
                """
                INSERT INTO cfb_matchups (league_id, season, week, home_team_id, away_team_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(league_id, season, week, home_team_id, away_team_id) DO NOTHING
                """,
                (league_id, season, week, home_id, away_id),
            )
        self.conn.commit()
        return len(pairs)

    def get_cfb_matchups(self, league_id: str, season: int, week: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.*, ht.team_name AS home_team_name, at.team_name AS away_team_name
            FROM cfb_matchups m
            JOIN cfb_league_teams ht ON m.home_team_id = ht.league_team_id
            JOIN cfb_league_teams at ON m.away_team_id = at.league_team_id
            WHERE m.league_id = ? AND m.season = ? AND m.week = ?
            ORDER BY m.matchup_id
            """,
            (league_id, season, week),
        ).fetchall()
        return [dict(r) for r in rows]

    def score_cfb_matchups(self, league_id: str, season: int, week: int) -> list[dict]:
        week_scores = {
            s["league_team_id"]: s["points"] for s in self.score_cfb_league_week(league_id, season, week)
        }
        matchups = self.get_cfb_matchups(league_id, season, week)
        results = []
        for m in matchups:
            home_score = float(week_scores.get(m["home_team_id"], 0.0))
            away_score = float(week_scores.get(m["away_team_id"], 0.0))
            self.conn.execute(
                """
                UPDATE cfb_matchups SET home_score = ?, away_score = ?
                WHERE league_id = ? AND season = ? AND week = ?
                  AND home_team_id = ? AND away_team_id = ?
                """,
                (home_score, away_score, league_id, season, week, m["home_team_id"], m["away_team_id"]),
            )
            if home_score > away_score:
                self.conn.execute(
                    "UPDATE cfb_league_teams SET wins = wins + 1 WHERE league_team_id = ?",
                    (m["home_team_id"],),
                )
                self.conn.execute(
                    "UPDATE cfb_league_teams SET losses = losses + 1 WHERE league_team_id = ?",
                    (m["away_team_id"],),
                )
            elif away_score > home_score:
                self.conn.execute(
                    "UPDATE cfb_league_teams SET wins = wins + 1 WHERE league_team_id = ?",
                    (m["away_team_id"],),
                )
                self.conn.execute(
                    "UPDATE cfb_league_teams SET losses = losses + 1 WHERE league_team_id = ?",
                    (m["home_team_id"],),
                )
            results.append(
                {
                    **m,
                    "home_score": home_score,
                    "away_score": away_score,
                }
            )
        self.conn.commit()
        return results

    # ==================== CFB LEAGUE SETTINGS & LOCKS ====================

    DEFAULT_CFB_LEAGUE_SETTINGS: dict = {
        "waiver_type": "faab",
        "faab_budget": 100.0,
        "waiver_run_day": 3,
        "waiver_run_hour_utc": 8,
        "trade_deadline_week": 12,
        "trade_review_hours": 24,
        "veto_threshold": 0,
        "playoff_teams": 4,
        "playoff_start_week": 15,
        "regular_season_weeks": 14,
        "lineup_lock": "individual_game",
    }

    def seed_cfb_league_settings(self, league_id: str) -> None:
        defaults = self.DEFAULT_CFB_LEAGUE_SETTINGS
        self.conn.execute(
            """
            INSERT INTO cfb_league_settings (
                league_id, waiver_type, faab_budget, waiver_run_day, waiver_run_hour_utc,
                trade_deadline_week, trade_review_hours, veto_threshold,
                playoff_teams, playoff_start_week, regular_season_weeks, lineup_lock
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id) DO NOTHING
            """,
            (
                league_id,
                defaults["waiver_type"],
                defaults["faab_budget"],
                defaults["waiver_run_day"],
                defaults["waiver_run_hour_utc"],
                defaults["trade_deadline_week"],
                defaults["trade_review_hours"],
                defaults["veto_threshold"],
                defaults["playoff_teams"],
                defaults["playoff_start_week"],
                defaults["regular_season_weeks"],
                defaults["lineup_lock"],
            ),
        )
        self.conn.commit()

    def get_cfb_league_settings(self, league_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM cfb_league_settings WHERE league_id = ?",
            (league_id,),
        ).fetchone()
        if row:
            return dict(row)
        return {"league_id": league_id, **self.DEFAULT_CFB_LEAGUE_SETTINGS}

    def update_cfb_league_settings(self, league_id: str, updates: dict) -> dict:
        allowed = set(self.DEFAULT_CFB_LEAGUE_SETTINGS.keys())
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return self.get_cfb_league_settings(league_id)
        self.seed_cfb_league_settings(league_id)
        set_sql = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE cfb_league_settings SET {set_sql}, updated_at = CURRENT_TIMESTAMP WHERE league_id = ?",
            (*fields.values(), league_id),
        )
        self.conn.commit()
        return self.get_cfb_league_settings(league_id)

    def build_cfb_game_locks(self, season: int) -> int:
        """Populate cfb_game_locks from cfb_games + cfb_teams."""
        games = self.get_cfb_games(season=season, finished_only=False)
        teams = self.get_cfb_teams(season=season)
        if games.empty or teams.empty:
            return 0
        abbr_to_key: dict[str, str] = {}
        for _, t in teams.iterrows():
            abbr = t.get("abbreviation") or t.get("team_key")
            if abbr:
                abbr_to_key[str(abbr).upper()] = t["team_key"]
            abbr_to_key[str(t["team_key"]).upper()] = t["team_key"]
        count = 0
        for _, g in games.iterrows():
            game_id = g["game_id"]
            week = g.get("week")
            lock_time = g.get("game_date") or ""
            if not lock_time or week is None:
                continue
            for col, abbr_col in (("home", "home_abbreviation"), ("away", "away_abbreviation")):
                abbr = g.get(abbr_col) or g.get(f"{col}_team")
                if not abbr:
                    continue
                team_key = abbr_to_key.get(str(abbr).upper())
                if not team_key:
                    continue
                self.conn.execute(
                    """
                    INSERT INTO cfb_game_locks (game_id, season, week, team_key, lock_time_utc)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(game_id, team_key) DO UPDATE SET lock_time_utc = excluded.lock_time_utc
                    """,
                    (game_id, season, int(week), team_key, str(lock_time)),
                )
                count += 1
        self.conn.commit()
        return count

    def is_player_locked(self, league_id: str, player_id: int, season: int, week: int) -> bool:
        """Return True if the player cannot be moved into/out of lineup."""
        from datetime import datetime, timezone

        settings = self.get_cfb_league_settings(league_id)
        lock_mode = settings.get("lineup_lock", "individual_game")
        player = pd.read_sql(
            "SELECT team_key FROM cfb_players WHERE player_id = ? AND season = ?",
            self.conn,
            params=[player_id, season],
        )
        if player.empty:
            return False
        team_key = player.iloc[0]["team_key"]
        now = datetime.now(timezone.utc)

        if lock_mode == "weekly":
            locks = pd.read_sql(
                """
                SELECT MIN(lock_time_utc) AS first_lock
                FROM cfb_game_locks
                WHERE season = ? AND week = ? AND team_key = ?
                """,
                self.conn,
                params=[season, week, team_key],
            )
            if locks.empty or locks.iloc[0]["first_lock"] is None:
                return False
            try:
                lock_dt = datetime.fromisoformat(str(locks.iloc[0]["first_lock"]).replace("Z", "+00:00"))
                if lock_dt.tzinfo is None:
                    lock_dt = lock_dt.replace(tzinfo=timezone.utc)
                return now >= lock_dt
            except ValueError:
                return False

        row = self.conn.execute(
            """
            SELECT lock_time_utc FROM cfb_game_locks
            WHERE season = ? AND week = ? AND team_key = ?
            ORDER BY lock_time_utc LIMIT 1
            """,
            (season, week, team_key),
        ).fetchone()
        if not row or not row[0]:
            return False
        try:
            lock_dt = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if lock_dt.tzinfo is None:
                lock_dt = lock_dt.replace(tzinfo=timezone.utc)
            return now >= lock_dt
        except ValueError:
            return False

    def seed_cfb_dst_players(self, season: int, conferences: Optional[list[str]] = None) -> int:
        """Create one rosterable team DST row per eligible team."""
        from ffpy.integrations.cfbd import DEFAULT_CONFERENCES

        confs = conferences or list(DEFAULT_CONFERENCES)
        teams = self.get_cfb_teams(season=season)
        if teams.empty:
            return 0
        eligible = teams[teams["conference"].isin(confs)] if "conference" in teams.columns else teams

        self.conn.execute(
            """
            UPDATE cfb_players
            SET position = 'DEF', fantasy_eligible = 0, updated_at = CURRENT_TIMESTAMP
            WHERE season = ? AND position = 'DST' AND full_name NOT LIKE '% DST'
            """,
            (season,),
        )

        count = 0
        skipped = 0
        for _, t in eligible.iterrows():
            school = t.get("school") or t["team_key"]
            full_name = f"{school} DST"
            existing = self.conn.execute(
                """
                SELECT player_id FROM cfb_players
                WHERE season = ? AND team_key = ? AND full_name = ?
                """,
                (season, t["team_key"], full_name),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            self.conn.execute(
                """
                INSERT INTO cfb_players (
                    season, full_name, position, team_key, conference,
                    conference_eligible, fantasy_eligible
                ) VALUES (?, ?, 'DST', ?, ?, 1, 1)
                """,
                (season, full_name, t["team_key"], t.get("conference")),
            )
            count += 1
        self.conn.commit()
        self._last_dst_seed_skipped = skipped
        return count

    # ==================== CFB DRAFT ====================

    def create_cfb_draft(self, draft: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_drafts (
                draft_id, league_id, status, draft_type, current_pick, order_json, settings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft["draft_id"],
                draft["league_id"],
                draft.get("status", "active"),
                draft.get("draft_type", "snake"),
                draft.get("current_pick", 1),
                draft["order_json"],
                draft.get("settings_json"),
            ),
        )
        self.conn.commit()

    def get_cfb_draft(self, league_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM cfb_drafts WHERE league_id = ?",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_cfb_draft_by_id(self, draft_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM cfb_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def update_cfb_draft(self, draft_id: str, updates: dict) -> None:
        allowed = {"status", "current_pick", "order_json", "settings_json"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        set_sql = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE cfb_drafts SET {set_sql}, updated_at = CURRENT_TIMESTAMP WHERE draft_id = ?",
            (*fields.values(), draft_id),
        )
        self.conn.commit()

    def add_cfb_draft_pick(self, pick: dict) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO cfb_draft_picks (
                draft_id, pick_number, round, team_id, player_id, picked_at, is_autopick
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (
                pick["draft_id"],
                pick["pick_number"],
                pick["round"],
                pick["team_id"],
                pick["player_id"],
                pick.get("is_autopick", 0),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get_cfb_draft_picks(self, draft_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT p.*, pl.full_name, pl.position, pl.team_key
            FROM cfb_draft_picks p
            LEFT JOIN cfb_players pl ON p.player_id = pl.player_id
            WHERE p.draft_id = ?
            ORDER BY p.pick_number
            """,
            (draft_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ==================== CFB ADP ====================

    def store_cfb_adp(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        count = 0
        for _, row in df.iterrows():
            self.conn.execute(
                """
                INSERT INTO cfb_adp (season, player_id, rank, source, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(season, player_id, source) DO UPDATE SET
                    rank = excluded.rank,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(row["season"]),
                    int(row["player_id"]),
                    int(row["rank"]),
                    row.get("source", "projections"),
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def get_cfb_adp(self, season: int, source: str = "projections") -> pd.DataFrame:
        return pd.read_sql(
            """
            SELECT a.*, p.full_name, p.position, p.team_key, p.conference
            FROM cfb_adp a
            JOIN cfb_players p ON a.player_id = p.player_id AND a.season = p.season
            WHERE a.season = ? AND a.source = ?
            ORDER BY a.rank
            """,
            self.conn,
            params=[season, source],
        )

    def create_cfb_transaction(self, tx: dict) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO cfb_transactions (
                league_id, league_team_id, tx_type, player_id, drop_player_id,
                faab_bid, status, week, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx["league_id"],
                tx["league_team_id"],
                tx["tx_type"],
                tx["player_id"],
                tx.get("drop_player_id"),
                tx.get("faab_bid"),
                tx.get("status", "pending"),
                tx.get("week"),
                tx.get("priority", 0),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_cfb_transaction(self, transaction_id: int, updates: dict) -> None:
        allowed = {"status", "processed_at", "failure_reason", "priority"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        set_sql = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE cfb_transactions SET {set_sql} WHERE transaction_id = ?",
            (*fields.values(), transaction_id),
        )
        self.conn.commit()

    def list_cfb_transactions(
        self,
        league_id: str,
        status: Optional[str] = None,
        week: Optional[int] = None,
    ) -> list[dict]:
        query = "SELECT * FROM cfb_transactions WHERE league_id = ?"
        params: list = [league_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if week is not None:
            query += " AND week = ?"
            params.append(week)
        query += " ORDER BY created_at DESC"
        cursor = self.conn.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]

    def log_cfb_waiver_run(self, league_id: str, season: int, week: int, processed: int, failed: int) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO cfb_waiver_runs (league_id, season, week, claims_processed, claims_failed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (league_id, season, week, processed, failed),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def decrement_cfb_faab(self, league_team_id: str, amount: float) -> None:
        self.conn.execute(
            "UPDATE cfb_league_teams SET faab_budget = faab_budget - ? WHERE league_team_id = ?",
            (amount, league_team_id),
        )
        self.conn.commit()

    # ==================== CFB TRADES ====================

    def create_cfb_trade(self, trade: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_trades (
                trade_id, league_id, status, proposer_team_id, recipient_team_id, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                trade["trade_id"],
                trade["league_id"],
                trade.get("status", "proposed"),
                trade["proposer_team_id"],
                trade["recipient_team_id"],
                trade.get("expires_at"),
            ),
        )
        self.conn.commit()

    def add_cfb_trade_item(self, item: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_trade_items (trade_id, player_id, from_team_id, to_team_id)
            VALUES (?, ?, ?, ?)
            """,
            (item["trade_id"], item["player_id"], item["from_team_id"], item["to_team_id"]),
        )
        self.conn.commit()

    def get_cfb_trade(self, trade_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM cfb_trades WHERE trade_id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None

    def list_cfb_trades(self, league_id: str, status: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM cfb_trades WHERE league_id = ?"
        params: list = [league_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_cfb_trade_items(self, trade_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT ti.*, p.full_name, p.position
            FROM cfb_trade_items ti
            LEFT JOIN cfb_players p ON ti.player_id = p.player_id
            WHERE ti.trade_id = ?
            """,
            (trade_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_cfb_trade_status(self, trade_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE cfb_trades SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE trade_id = ?",
            (status, trade_id),
        )
        self.conn.commit()

    def add_cfb_trade_vote(self, trade_id: str, team_id: str, vote: str) -> None:
        self.conn.execute(
            """
            INSERT INTO cfb_trade_votes (trade_id, team_id, vote)
            VALUES (?, ?, ?)
            ON CONFLICT(trade_id, team_id) DO UPDATE SET vote = excluded.vote
            """,
            (trade_id, team_id, vote),
        )
        self.conn.commit()

    def count_cfb_trade_vetoes(self, trade_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM cfb_trade_votes WHERE trade_id = ? AND vote = 'veto'",
            (trade_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def audit_cfb_data(self, season: Optional[int] = None) -> dict:
        cursor = self.conn.cursor()
        tables = [
            "cfb_teams",
            "cfb_players",
            "cfb_player_game_stats",
            "cfb_team_defense_stats",
            "cfb_fantasy_points",
            "cfb_projections",
            "cfb_games",
            "cfb_rosters",
        ]
        results: dict = {}
        for table in tables:
            try:
                if season and table in ("cfb_teams", "cfb_players", "cfb_games", "cfb_rosters"):
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE season = ?", (season,))
                elif season and "season" in table:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE season = ?", (season,))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                results[f"{table}_rows"] = int(cursor.fetchone()[0])
            except Exception:
                results[f"{table}_rows"] = -1
        return results

    # ==================== VEGAS IMPLIED TEAM TOTALS ====================

    def get_implied_team_totals(
        self,
        season: int,
        week: Optional[int] = None,
        team: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute implied team scores from Vegas spread and total lines.

        Implied home score = (total_line - spread_line) / 2
        Implied away score = (total_line + spread_line) / 2

        Args:
            season: Season year
            week: Optional week filter
            team: Optional team filter (home or away)

        Returns:
            DataFrame with game_id, season, week, home_team, away_team,
            spread_line, total_line, implied_home_score, implied_away_score
        """
        conditions: list[str] = ["g.season = ?"]
        params: list = [season]

        if week is not None:
            conditions.append("g.week = ?")
            params.append(week)
        if team is not None:
            conditions.append("(g.home_team = ? OR g.away_team = ?)")
            params.extend([team, team])

        where_sql = " AND ".join(conditions)
        query = f"""
            SELECT
                g.game_id,
                g.season,
                g.week,
                g.game_date,
                g.home_team,
                g.away_team,
                g.spread_line,
                g.total_line,
                CASE
                    WHEN g.spread_line IS NOT NULL AND g.total_line IS NOT NULL
                    THEN ROUND((g.total_line - g.spread_line) / 2.0, 1)
                    ELSE NULL
                END AS implied_home_score,
                CASE
                    WHEN g.spread_line IS NOT NULL AND g.total_line IS NOT NULL
                    THEN ROUND((g.total_line + g.spread_line) / 2.0, 1)
                    ELSE NULL
                END AS implied_away_score
            FROM games g
            WHERE {where_sql}
            ORDER BY g.week, g.game_date
        """
        return pd.read_sql(query, self.conn, params=params)

    # ==================== OFFENSIVE LINE STATS (Phase 3) ====================

    def compute_offensive_line_stats(self, season: int, weeks: int = 4) -> pd.DataFrame:
        """Compute rolling offensive line stats from plays table.

        For each team-week, calculates pressure rate, sack rate, and
        adjusted line yards from the plays table, then returns a 4-week
        rolling average.

        Args:
            season: Season year
            weeks: Rolling window size (default 4)

        Returns:
            DataFrame with offensive_line_stats columns
        """
        # Check plays table exists (it's only created by migration 002)
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plays'")
        if not cursor.fetchone():
            return pd.DataFrame()

        query = """
            SELECT
                posteam AS team,
                week,
                COUNT(*) AS dropbacks,
                SUM(CASE WHEN sack = 1 THEN 1 ELSE 0 END) AS sacks
            FROM plays
            WHERE season = ?
              AND qb_dropback = 1
              AND week <= (SELECT MAX(week) FROM plays WHERE season = ?)
            GROUP BY posteam, week
        """
        pass_df = pd.read_sql(query, self.conn, params=[season, season])

        rush_query = """
            SELECT
                posteam AS team,
                week,
                COUNT(*) AS rush_attempts,
                SUM(yards_gained) AS rush_yards,
                SUM(CASE WHEN yardline_100 IS NOT NULL AND yards_gained IS NOT NULL
                         THEN yards_gained
                         ELSE 0 END) AS raw_yards,
                SUM(CASE WHEN yards_gained <= 0 THEN yards_gained * 1.2
                         WHEN yards_gained <= 4 THEN yards_gained * 1.0
                         WHEN yards_gained <= 10 THEN yards_gained * 0.5
                         ELSE 0.0 END) AS adjusted_yards
            FROM plays
            WHERE season = ?
              AND play_type = 'run'
              AND week <= (SELECT MAX(week) FROM plays WHERE season = ?)
            GROUP BY posteam, week
        """
        rush_df = pd.read_sql(rush_query, self.conn, params=[season, season])

        if pass_df.empty and rush_df.empty:
            return pd.DataFrame()

        merged = pd.merge(pass_df, rush_df, on=["team", "week"], how="outer").fillna(0)

        merged["sack_rate"] = merged["sacks"] / merged["dropbacks"].replace(0, float("nan"))
        merged["adjusted_line_yards"] = merged["adjusted_yards"] / merged["rush_attempts"].replace(
            0, float("nan")
        )
        merged["pressure_rate"] = merged["sack_rate"] * 1.5  # approximate: pressure rate ≈ 1.5× sack rate
        merged["yards_before_contact_per_rush"] = 0.0  # not available in basic PBP
        merged["yards_after_contact_per_rush"] = 0.0
        merged["season"] = season

        result = merged[
            [
                "team",
                "season",
                "week",
                "pressure_rate",
                "sack_rate",
                "adjusted_line_yards",
                "yards_before_contact_per_rush",
                "yards_after_contact_per_rush",
                "rush_attempts",
                "dropbacks",
            ]
        ].copy()

        # Compute rolling averages
        result = result.sort_values(["team", "week"])
        rolling_cols = ["pressure_rate", "sack_rate", "adjusted_line_yards"]
        for col in rolling_cols:
            result[f"{col}_rolling"] = result.groupby("team")[col].transform(
                lambda x: x.rolling(window=weeks, min_periods=1).mean()
            )

        return result

    def store_offensive_line_stats(self, df: pd.DataFrame, season: int) -> int:
        """Store offensive line stats.

        Args:
            df: DataFrame with columns matching offensive_line_stats schema
            season: Season year

        Returns:
            Number of rows stored
        """
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(offensive_line_stats)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("ol_stat_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        update_sql = ", ".join(
            f"{col}=excluded.{col}" for col in available_cols if col not in ("team", "season", "week")
        )
        cursor.executemany(
            f"""INSERT INTO offensive_line_stats ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(team, season, week) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_offensive_line_stats(
        self,
        team: Optional[str] = None,
        season: Optional[int] = None,
        week: Optional[int] = None,
    ) -> pd.DataFrame:
        """Retrieve offensive line stats.

        Args:
            team: Optional team filter
            season: Optional season filter
            week: Optional week filter

        Returns:
            DataFrame with offensive line stats
        """
        conditions: list[str] = []
        params: list = []
        if team is not None:
            conditions.append("team = ?")
            params.append(team)
        if season is not None:
            conditions.append("season = ?")
            params.append(season)
        if week is not None:
            conditions.append("week = ?")
            params.append(week)

        where_sql = " AND ".join(conditions) if conditions else "1"
        query = f"SELECT * FROM offensive_line_stats WHERE {where_sql} ORDER BY team, week"
        return pd.read_sql(query, self.conn, params=params)

    # ==================== DEFENSIVE MATCHUP STATS ====================

    def get_defensive_matchup_stats(
        self,
        team: str,
        position: str,
        season: int,
        weeks: int = 4,
    ) -> Optional[Dict[str, float]]:
        """Compute rolling defensive matchup stats for a defence.

        Uses the ``plays`` table to calculate, over the last *weeks* games,
        the average EPA allowed per play and fantasy points allowed per game
        by a defence against a given position.

        Args:
            team: Opponent defence team abbreviation (e.g. ``"BUF"``).
            position: Position to filter against (QB, RB, WR, TE).
            season: Season year.
            weeks: Number of weeks to look back (default 4).

        Returns:
            Dict with ``epa_allowed_per_play`` and ``fp_allowed_per_game``,
            or ``None`` if insufficient data.
        """
        # Map position to EPA columns
        if position == "QB":
            epa_condition = "play_type = 'pass'"
        elif position in ("WR", "TE"):
            epa_condition = "play_type = 'pass' AND receiver_player_name IS NOT NULL"
        elif position == "RB":
            epa_condition = "play_type = 'run'"
        else:
            epa_condition = "1"

        query = f"""
            SELECT
                COUNT(*) AS n_plays,
                AVG(epa) AS avg_epa,
                SUM(CASE WHEN touchdown = 1 THEN 6
                         WHEN play_type = 'pass' AND complete_pass = 1 THEN 0.5
                         ELSE 0 END) AS fantasy_points_raw
            FROM plays
            WHERE defteam = ?
              AND season = ?
              AND week >= (SELECT MAX(week) - ? + 1 FROM plays WHERE defteam = ? AND season = ?)
              AND week <= (SELECT MAX(week) FROM plays WHERE defteam = ? AND season = ?)
              AND {epa_condition}
        """
        params = [team, season, weeks, team, season, team, season]

        df = pd.read_sql(query, self.conn, params=params)

        if df.empty or df["n_plays"].iloc[0] is None or df["n_plays"].iloc[0] < 10:
            return None

        row = df.iloc[0]
        # Rough fantasy-point proxy (TD = 6, reception = 0.5 in PPR)
        n_plays_val = int(row["n_plays"])
        avg_epa_val = float(row["avg_epa"]) if row["avg_epa"] is not None else 0.0
        fp_raw = float(row["fantasy_points_raw"]) if row["fantasy_points_raw"] is not None else 0.0

        # Estimate games from plays (rough: ~60 plays/game)
        est_games = max(1, n_plays_val / 60)

        return {
            "epa_allowed_per_play": round(avg_epa_val, 4),
            "fp_allowed_per_game": round(fp_raw / est_games, 1),
            "n_plays": n_plays_val,
        }

    # ==================== GAME WEATHER ====================

    def store_game_weather(self, df: pd.DataFrame) -> int:
        """Store or update game weather data.

        Args:
            df: DataFrame with columns matching game_weather schema.

        Returns:
            Number of rows inserted or updated.
        """
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(game_weather)")
        schema_columns = {row[1] for row in cursor.fetchall()}

        available_cols = [
            col for col in df.columns if col in schema_columns and col not in ("weather_id", "created_at")
        ]
        if not available_cols:
            return 0

        column_sql = ", ".join(available_cols)
        placeholders = ", ".join("?" for _ in available_cols)
        update_sql = ", ".join(
            f"{col}=excluded.{col}" for col in available_cols if col not in ("game_id", "season", "week")
        )

        cursor.executemany(
            f"""INSERT INTO game_weather ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(game_id) DO UPDATE SET {update_sql}""",
            _sqlite_records(df[available_cols]),
        )
        self.conn.commit()
        return max(cursor.rowcount, 0)

    def get_game_weather(
        self,
        season: Optional[int] = None,
        week: Optional[int] = None,
        team: Optional[str] = None,
    ) -> pd.DataFrame:
        """Retrieve game weather data.

        Args:
            season: Optional season filter.
            week: Optional week filter.
            team: Optional team filter (home or away).

        Returns:
            DataFrame with game weather.
        """
        conditions: List[str] = []
        params: List = []

        if season is not None:
            conditions.append("gw.season = ?")
            params.append(season)
        if week is not None:
            conditions.append("gw.week = ?")
            params.append(week)
        if team is not None:
            conditions.append("(g.home_team = ? OR g.away_team = ?)")
            params.extend([team, team])

        where_sql = " AND ".join(conditions) if conditions else "1"

        query = f"""
            SELECT
                gw.*,
                g.home_team,
                g.away_team,
                g.game_date,
                g.stadium
            FROM game_weather gw
            JOIN games g ON gw.game_id = g.game_id
            WHERE {where_sql}
            ORDER BY gw.season, gw.week, g.game_date
        """
        return pd.read_sql(query, self.conn, params=params)

    # ==================== DATA QUALITY (Phase 4) ====================

    def audit_data_quality(self) -> Dict[str, Any]:
        """
        Run all data quality checks against the database.

        Returns:
            Dictionary with audit results per check
        """
        results: Dict[str, Any] = {}
        cursor = self.conn.cursor()

        # Check: views exist
        for view in ("vw_player_weeks", "vw_missing_games", "vw_duplicate_stats"):
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
                (view,),
            )
            results[f"view_{view}"] = cursor.fetchone() is not None

        # Check: missing games
        try:
            missing = pd.read_sql("SELECT COUNT(*) AS cnt FROM vw_missing_games", self.conn)
            results["missing_games_count"] = int(missing["cnt"].iloc[0])
        except Exception:
            results["missing_games_count"] = -1

        # Check: duplicate stats
        try:
            dups = pd.read_sql("SELECT COUNT(*) AS cnt FROM vw_duplicate_stats", self.conn)
            results["duplicate_stat_weeks"] = int(dups["cnt"].iloc[0])
        except Exception:
            results["duplicate_stat_weeks"] = -1

        # Check: table row counts
        tables = [
            "players",
            "actual_stats",
            "projections",
            "games",
            "plays",
            "snap_counts",
            "ftn_charting",
            "player_advanced_stats",
            "nextgen_stats",
            "player_injuries",
            "dfs_salaries",
            "adp",
            "depth_charts",
            "player_rosters",
            "cfb_games",
            "cfb_rosters",
            "cfb_plays",
            "cfb_teams",
            "cfb_players",
            "cfb_fantasy_points",
        ]
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                results[f"table_{table}_rows"] = int(cursor.fetchone()[0])
            except Exception:
                results[f"table_{table}_rows"] = -1

        return results

    # ==================== USER CREDENTIALS (League Import) ====================

    def store_user_credentials(self, user_id: str, provider: str, ciphertext: str, label: str = "") -> None:
        """Store or update encrypted credentials for a user/provider."""
        self.conn.execute(
            """
            INSERT INTO user_credentials (user_id, provider, encrypted, label)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, provider) DO UPDATE SET
                encrypted = excluded.encrypted,
                label = excluded.label,
                updated_at = CURRENT_TIMESTAMP
        """,
            (user_id, provider, ciphertext, label),
        )
        self.conn.commit()

    def get_user_credentials(self, user_id: str) -> list[dict]:
        """List stored credentials metadata (without ciphertext) for a user."""
        cursor = self.conn.execute(
            "SELECT cred_id, provider, label, created_at, updated_at FROM user_credentials WHERE user_id = ?",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_credential_ciphertext(self, user_id: str, provider: str) -> str | None:
        """Retrieve the encrypted credential blob for a user/provider."""
        cursor = self.conn.execute(
            "SELECT encrypted FROM user_credentials WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def delete_user_credentials(self, user_id: str, provider: str) -> None:
        """Delete stored credentials for a user/provider."""
        self.conn.execute(
            "DELETE FROM user_credentials WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        self.conn.commit()

    # ==================== USER LEAGUES (League Import) ====================

    def store_user_league(self, user_id: str, data: dict) -> str:
        """Store league metadata, teams, and matchups from an import."""
        league = data["league"]
        self.conn.execute(
            """
            INSERT INTO user_leagues
                (league_id, user_id, provider, league_name, season,
                 scoring_type, roster_size, num_teams, playoff_teams, league_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id) DO UPDATE SET
                league_name = excluded.league_name,
                league_json = excluded.league_json,
                refreshed_at = CURRENT_TIMESTAMP
        """,
            (
                league["league_id"],
                user_id,
                league["provider"],
                league["name"],
                league["season"],
                league.get("scoring_type"),
                league.get("roster_size"),
                league.get("num_teams"),
                league.get("playoff_teams"),
                json.dumps(league),
            ),
        )
        for team in data.get("teams", []):
            self.conn.execute(
                """
                INSERT INTO league_teams
                    (team_id, league_id, team_name, owner_name,
                     wins, losses, ties, points_for, points_against,
                     rank, roster_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = excluded.team_name,
                    owner_name = excluded.owner_name,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    ties = excluded.ties,
                    roster_json = excluded.roster_json,
                    points_for = excluded.points_for,
                    points_against = excluded.points_against
            """,
                (
                    team["team_id"],
                    league["league_id"],
                    team["name"],
                    team.get("owner"),
                    team.get("wins", 0),
                    team.get("losses", 0),
                    team.get("ties", 0),
                    team.get("points_for", 0),
                    team.get("points_against", 0),
                    team.get("rank"),
                    json.dumps(team.get("roster", [])),
                ),
            )
        for m in data.get("matchups", []):
            self.conn.execute(
                """
                INSERT INTO league_matchups
                    (league_id, week, home_team_id, away_team_id,
                     home_score, away_score, is_playoff, is_consolation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, week, home_team_id, away_team_id)
                DO UPDATE SET home_score=excluded.home_score,
                              away_score=excluded.away_score
            """,
                (
                    league["league_id"],
                    m["week"],
                    m["home_team_id"],
                    m["away_team_id"],
                    m.get("home_score"),
                    m.get("away_score"),
                    m.get("is_playoff", 0),
                    m.get("is_consolation", 0),
                ),
            )
        self.conn.commit()
        return league["league_id"]

    def get_user_leagues(self, user_id: str) -> list[dict]:
        """List all imported leagues for a user."""
        cursor = self.conn.execute(
            "SELECT * FROM user_leagues WHERE user_id = ? ORDER BY imported_at DESC",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_all_leagues(self) -> list[dict]:
        """List all imported leagues (local dev when auth is disabled)."""
        cursor = self.conn.execute(
            "SELECT * FROM user_leagues ORDER BY imported_at DESC",
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_user_league(self, league_id: str, user_id: str) -> dict | None:
        """Get a single league by ID, verifying user ownership."""
        cursor = self.conn.execute(
            "SELECT * FROM user_leagues WHERE league_id = ? AND user_id = ?",
            (league_id, user_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_league_by_id(self, league_id: str) -> dict | None:
        """Get a single league by ID without ownership check."""
        cursor = self.conn.execute(
            "SELECT * FROM user_leagues WHERE league_id = ?",
            (league_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_league_teams(self, league_id: str, user_id: str) -> list[dict]:
        """Get teams for a league, verifying user ownership."""
        cursor = self.conn.execute(
            """
            SELECT t.* FROM league_teams t
            JOIN user_leagues l ON t.league_id = l.league_id
            WHERE t.league_id = ? AND l.user_id = ?
            ORDER BY t.rank, t.points_for DESC
        """,
            (league_id, user_id),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_teams_for_league(self, league_id: str) -> list[dict]:
        """Get teams for a league without ownership check."""
        cursor = self.conn.execute(
            """
            SELECT * FROM league_teams
            WHERE league_id = ?
            ORDER BY rank, points_for DESC
        """,
            (league_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_league_matchups(self, league_id: str, week: int, user_id: str) -> list[dict]:
        """Get matchups for a league/week, verifying user ownership."""
        cursor = self.conn.execute(
            """
            SELECT m.* FROM league_matchups m
            JOIN user_leagues l ON m.league_id = l.league_id
            WHERE m.league_id = ? AND m.week = ? AND l.user_id = ?
            ORDER BY m.matchup_id
        """,
            (league_id, week, user_id),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_matchups_for_league(self, league_id: str, week: int) -> list[dict]:
        """Get matchups for a league/week without ownership check."""
        cursor = self.conn.execute(
            """
            SELECT * FROM league_matchups
            WHERE league_id = ? AND week = ?
            ORDER BY matchup_id
        """,
            (league_id, week),
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_user_league(self, league_id: str, user_id: str) -> None:
        """Delete a league owned by ``user_id``; teams/matchups cascade."""
        cursor = self.conn.execute(
            "DELETE FROM user_leagues WHERE league_id = ? AND user_id = ?",
            (league_id, user_id),
        )
        if cursor.rowcount:
            self.conn.commit()
