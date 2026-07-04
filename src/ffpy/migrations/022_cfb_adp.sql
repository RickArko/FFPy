-- CFB average draft position (projection-derived or CSV upload)

CREATE TABLE IF NOT EXISTS cfb_adp (
    adp_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    season          INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    source          TEXT NOT NULL DEFAULT 'projections',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, player_id, source)
);

CREATE INDEX IF NOT EXISTS idx_cfb_adp_season_rank ON cfb_adp(season, source, rank);
