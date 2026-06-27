-- FFPy Database Schema — Offensive Line Stats
-- Derived from plays table: pressure rate, sack rate, adjusted line yards.
--
-- Adjusted Line Yards formula (Football Outsiders):
--   0-4 yds: 100% value  |  5-10 yds: 50% value
--   11+ yds: 0% value    |  Loss: 120% penalty

CREATE TABLE IF NOT EXISTS offensive_line_stats (
    ol_stat_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team                TEXT NOT NULL,
    season              INTEGER NOT NULL,
    week                INTEGER NOT NULL,
    pressure_rate       REAL,        -- QB pressures / dropbacks
    sack_rate           REAL,        -- sacks / dropbacks
    adjusted_line_yards REAL,        -- FO-style rushing efficiency
    yards_before_contact_per_rush REAL,
    yards_after_contact_per_rush REAL,
    rush_attempts       INTEGER DEFAULT 0,
    dropbacks           INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team, season, week)
);

CREATE INDEX IF NOT EXISTS idx_ol_stats_team_season ON offensive_line_stats(team, season);
CREATE INDEX IF NOT EXISTS idx_ol_stats_season_week ON offensive_line_stats(season, week);
