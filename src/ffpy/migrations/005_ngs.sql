-- FFPy Database Schema - Next Gen Stats Migration
-- NFL Next Gen Stats via nflreadpy (available 2016+).
-- Covers passing (QB), receiving (WR/TE), and rushing (RB) metrics.

CREATE TABLE IF NOT EXISTS nextgen_stats (
    ngs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    season_type TEXT,
    week INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    team TEXT,
    position TEXT,
    player_gsis_id TEXT,
    -- Passing (QB)
    avg_time_to_throw REAL,
    avg_completed_air_yards REAL,
    avg_intended_air_yards REAL,
    avg_air_yards_differential REAL,
    aggressiveness REAL,
    completion_percentage_above_expectation REAL,
    -- Receiving (WR/TE)
    avg_cushion REAL,
    avg_separation REAL,
    avg_yac REAL,
    avg_expected_yac REAL,
    avg_yac_above_expectation REAL,
    -- Rushing (RB)
    expected_rush_yards REAL,
    rush_yards_over_expected REAL,
    rush_yards_over_expected_per_att REAL,
    avg_time_to_los REAL,
    efficiency REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, week, player_name)
);

CREATE INDEX IF NOT EXISTS idx_ngs_player
    ON nextgen_stats(player_name, season);
CREATE INDEX IF NOT EXISTS idx_ngs_season_week
    ON nextgen_stats(season, week);
