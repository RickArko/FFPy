-- FFPy Database Schema - DFS Salaries Migration
-- Weekly salary data from DraftKings, FanDuel, and other platforms.

CREATE TABLE IF NOT EXISTS dfs_salaries (
    dfs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    platform TEXT NOT NULL,
    player_name TEXT NOT NULL,
    salary INTEGER,
    position TEXT,
    team TEXT,
    opponent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, week, platform, player_name)
);

CREATE INDEX IF NOT EXISTS idx_dfs_player
    ON dfs_salaries(player_name, season, week);
CREATE INDEX IF NOT EXISTS idx_dfs_platform_week
    ON dfs_salaries(platform, season, week);
