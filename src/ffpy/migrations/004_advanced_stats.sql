-- FFPy Database Schema - Advanced Player Stats Migration
-- Derived analytics computed from existing plays + snap_counts + ftn_charting.
-- No new external data sources required.

CREATE TABLE IF NOT EXISTS player_advanced_stats (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    team TEXT,
    position TEXT,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    targets INTEGER DEFAULT 0,
    air_yards REAL DEFAULT 0,
    avg_target_distance REAL,
    target_share REAL,
    air_yards_share REAL,
    routes_run INTEGER DEFAULT 0,
    yards_after_catch_per_rec REAL,
    deep_targets INTEGER DEFAULT 0,
    red_zone_targets INTEGER DEFAULT 0,
    end_zone_targets INTEGER DEFAULT 0,
    snap_pct REAL DEFAULT 0.0,
    route_pct REAL DEFAULT 0.0,
    first_read_targets INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_name, season, week)
);

CREATE INDEX IF NOT EXISTS idx_adv_stats_player
    ON player_advanced_stats(player_name, season);
CREATE INDEX IF NOT EXISTS idx_adv_stats_season_week
    ON player_advanced_stats(season, week);
