-- CFB league commissioner settings and game lock times

CREATE TABLE IF NOT EXISTS cfb_league_settings (
    league_id               TEXT PRIMARY KEY REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    waiver_type             TEXT NOT NULL DEFAULT 'faab',
    faab_budget             REAL NOT NULL DEFAULT 100,
    waiver_run_day          INTEGER NOT NULL DEFAULT 3,
    waiver_run_hour_utc     INTEGER NOT NULL DEFAULT 8,
    trade_deadline_week     INTEGER NOT NULL DEFAULT 12,
    trade_review_hours      INTEGER NOT NULL DEFAULT 24,
    veto_threshold          INTEGER NOT NULL DEFAULT 0,
    playoff_teams           INTEGER NOT NULL DEFAULT 4,
    playoff_start_week      INTEGER NOT NULL DEFAULT 15,
    regular_season_weeks    INTEGER NOT NULL DEFAULT 14,
    lineup_lock             TEXT NOT NULL DEFAULT 'individual_game',
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cfb_game_locks (
    lock_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    team_key        TEXT NOT NULL,
    lock_time_utc   TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, team_key)
);

CREATE INDEX IF NOT EXISTS idx_cfb_game_locks_season_week ON cfb_game_locks(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_game_locks_team_week ON cfb_game_locks(team_key, season, week);
