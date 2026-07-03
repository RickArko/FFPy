-- CFB snake/auction draft state

CREATE TABLE IF NOT EXISTS cfb_drafts (
    draft_id        TEXT PRIMARY KEY,
    league_id       TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'pending',
    draft_type      TEXT NOT NULL DEFAULT 'snake',
    current_pick    INTEGER NOT NULL DEFAULT 1,
    order_json      TEXT NOT NULL,
    settings_json   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_id)
);

CREATE TABLE IF NOT EXISTS cfb_draft_picks (
    pick_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id        TEXT NOT NULL REFERENCES cfb_drafts(draft_id) ON DELETE CASCADE,
    pick_number     INTEGER NOT NULL,
    round           INTEGER NOT NULL,
    team_id         TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id),
    player_id       INTEGER,
    picked_at       TIMESTAMP,
    is_autopick     INTEGER DEFAULT 0,
    UNIQUE(draft_id, pick_number)
);

CREATE INDEX IF NOT EXISTS idx_cfb_draft_picks_draft ON cfb_draft_picks(draft_id);
