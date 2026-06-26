-- FFPy Database Schema - Player Injuries Migration
-- Injury reports via nflreadpy (available across seasons).

CREATE TABLE IF NOT EXISTS player_injuries (
    injury_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    team TEXT,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    practice_status TEXT,
    injury_type TEXT,
    game_status TEXT,
    date_reported TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, week, player_name)
);

CREATE INDEX IF NOT EXISTS idx_injuries_player
    ON player_injuries(player_name, season);
CREATE INDEX IF NOT EXISTS idx_injuries_season_week
    ON player_injuries(season, week);
