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
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent / "migrations" / "001_initial_schema.sql"

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        self.conn.executescript(schema_sql)
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
