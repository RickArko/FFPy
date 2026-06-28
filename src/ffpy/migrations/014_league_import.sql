-- Encrypted credential store (one row per user per provider)
CREATE TABLE IF NOT EXISTS user_credentials (
    cred_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    provider   TEXT NOT NULL CHECK(provider IN ('espn','yahoo','sleeper')),
    encrypted  TEXT NOT NULL,          -- AES-GCM encrypted JSON blob
    label      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider)
);

-- League metadata
CREATE TABLE IF NOT EXISTS user_leagues (
    league_id      TEXT PRIMARY KEY,   -- e.g. 'espn:123456', 'yahoo:389.l.789012'
    user_id        TEXT NOT NULL,
    provider       TEXT NOT NULL,
    league_name    TEXT,
    season         INTEGER NOT NULL,
    scoring_type   TEXT,               -- 'ppr', 'half_ppr', 'standard', 'custom'
    roster_size    INTEGER,
    num_teams      INTEGER,
    playoff_teams  INTEGER,
    league_json    TEXT,               -- raw settings snapshot
    imported_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    refreshed_at   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_leagues_user ON user_leagues(user_id);

-- Teams within imported leagues
CREATE TABLE IF NOT EXISTS league_teams (
    team_id      TEXT PRIMARY KEY,     -- e.g. 'espn:123456:1'
    league_id    TEXT NOT NULL REFERENCES user_leagues(league_id) ON DELETE CASCADE,
    team_name    TEXT,
    owner_name   TEXT,
    wins         INTEGER DEFAULT 0,
    losses       INTEGER DEFAULT 0,
    ties         INTEGER DEFAULT 0,
    points_for   REAL DEFAULT 0,
    points_against REAL DEFAULT 0,
    rank         INTEGER,
    roster_json  TEXT,                 -- roster snapshot at import
    waiver_rank  INTEGER,
    faab_budget  REAL,
    imported_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_league_teams_league ON league_teams(league_id);

-- Weekly matchups
CREATE TABLE IF NOT EXISTS league_matchups (
    matchup_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id     TEXT NOT NULL REFERENCES user_leagues(league_id) ON DELETE CASCADE,
    week          INTEGER NOT NULL,
    home_team_id  TEXT NOT NULL,
    away_team_id  TEXT NOT NULL,
    home_score    REAL,
    away_score    REAL,
    is_playoff    INTEGER DEFAULT 0,
    is_consolation INTEGER DEFAULT 0,
    UNIQUE(league_id, week, home_team_id, away_team_id)
);

CREATE INDEX IF NOT EXISTS idx_matchups_league_week ON league_matchups(league_id, week);
