-- Extend CFB transactions for FAAB waiver processing (column adds handled idempotently in database.py)

CREATE TABLE IF NOT EXISTS cfb_waiver_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id       TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    claims_processed INTEGER DEFAULT 0,
    claims_failed   INTEGER DEFAULT 0,
    run_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cfb_waiver_runs_league ON cfb_waiver_runs(league_id, week);
