-- FFPy Database Schema - Initial Migration
-- Focus: Historical actual player statistics

-- Core player registry
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    nfl_id TEXT UNIQUE,  -- ESPN player ID or other unique identifier
    team TEXT,
    position TEXT NOT NULL CHECK(position IN ('QB', 'RB', 'WR', 'TE', 'K', 'DST')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Actual game results (what actually happened)
CREATE TABLE IF NOT EXISTS actual_stats (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL CHECK(week BETWEEN 1 AND 18),

    -- Actual performance
    actual_points REAL,

    -- QB stats
    passing_yards INTEGER,
    passing_tds REAL,  -- Can be fractional in some scoring systems
    interceptions INTEGER,

    -- Rushing stats (all positions)
    rushing_yards INTEGER,
    rushing_tds REAL,

    -- Receiving stats (RB/WR/TE)
    receiving_yards INTEGER,
    receiving_tds REAL,
    receptions INTEGER,

    -- Game context
    opponent TEXT,
    home_away TEXT,
    game_date DATE,

    -- Metadata
    source TEXT DEFAULT 'espn',  -- Track data source
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE,
    UNIQUE(player_id, season, week)
);

-- Projections from various sources (to be populated from actuals-based models)
CREATE TABLE IF NOT EXISTS projections (
    projection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL CHECK(week BETWEEN 1 AND 18),
    source TEXT NOT NULL CHECK(source IN ('espn', 'sportsdata', 'ffpy_model', 'sample')),

    -- Core projection
    projected_points REAL,

    -- QB stats
    passing_yards REAL,
    passing_tds REAL,
    interceptions REAL,

    -- Rushing stats
    rushing_yards REAL,
    rushing_tds REAL,

    -- Receiving stats
    receiving_yards REAL,
    receiving_tds REAL,
    receptions REAL,

    -- Metadata
    opponent TEXT,
    home_away TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE,
    UNIQUE(player_id, season, week, source)
);

-- API request log (avoid duplicate requests)
CREATE TABLE IF NOT EXISTS api_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    request_type TEXT NOT NULL,  -- 'actuals' or 'projections'
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_actual_stats_player_season ON actual_stats(player_id, season, week);
CREATE INDEX IF NOT EXISTS idx_actual_stats_week ON actual_stats(season, week);
CREATE INDEX IF NOT EXISTS idx_projections_player_season ON projections(player_id, season, week);
CREATE INDEX IF NOT EXISTS idx_projections_week ON projections(season, week);
CREATE INDEX IF NOT EXISTS idx_api_requests_lookup ON api_requests(source, season, week);
CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team);
