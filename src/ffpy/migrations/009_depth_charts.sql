-- FFPy Database Schema - Depth Charts Migration
-- Weekly team depth charts (available via nflreadpy).

CREATE TABLE IF NOT EXISTS depth_charts (
    dc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    position TEXT NOT NULL,
    player_name TEXT NOT NULL,
    depth_spot INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team, season, week, position, depth_spot)
);

CREATE INDEX IF NOT EXISTS idx_dc_team
    ON depth_charts(team, season, week);
CREATE INDEX IF NOT EXISTS idx_dc_player
    ON depth_charts(player_name, season);
