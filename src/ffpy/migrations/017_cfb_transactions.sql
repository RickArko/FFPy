-- FFPy Database Schema — CFB league transactions (waiver/trade stub)

CREATE TABLE IF NOT EXISTS cfb_transactions (
    transaction_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id         TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    league_team_id    TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id) ON DELETE CASCADE,
    tx_type           TEXT NOT NULL,
    player_id         INTEGER NOT NULL,
    faab_bid          REAL,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cfb_tx_league ON cfb_transactions(league_id, status);
