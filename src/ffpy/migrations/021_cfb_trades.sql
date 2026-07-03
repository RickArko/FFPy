-- CFB trade packages and league veto votes

CREATE TABLE IF NOT EXISTS cfb_trades (
    trade_id            TEXT PRIMARY KEY,
    league_id           TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'proposed',
    proposer_team_id    TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id),
    recipient_team_id   TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id),
    expires_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cfb_trade_items (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT NOT NULL REFERENCES cfb_trades(trade_id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL,
    from_team_id    TEXT NOT NULL,
    to_team_id      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cfb_trade_votes (
    vote_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT NOT NULL REFERENCES cfb_trades(trade_id) ON DELETE CASCADE,
    team_id         TEXT NOT NULL,
    vote            TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_trades_league ON cfb_trades(league_id, status);
