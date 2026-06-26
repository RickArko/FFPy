-- FFPy Database Schema - Average Draft Position Migration
-- ADP data across platforms (FantasyPros, Underdog, etc.).

CREATE TABLE IF NOT EXISTS adp (
    adp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    position TEXT,
    platform TEXT NOT NULL,
    adp REAL,
    adp_high REAL,
    adp_low REAL,
    draft_date TEXT,
    season INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_name, platform, season)
);

CREATE INDEX IF NOT EXISTS idx_adp_player
    ON adp(player_name, season);
CREATE INDEX IF NOT EXISTS idx_adp_platform
    ON adp(platform, season);
