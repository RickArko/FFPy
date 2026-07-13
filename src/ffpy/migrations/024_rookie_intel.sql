-- Curated rookie watchlist and expert content for draft-season intel.

CREATE TABLE IF NOT EXISTS rookie_watchlist (
    watchlist_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    season          INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT NOT NULL,
    rank_in_position INTEGER NOT NULL DEFAULT 1,
    adp             REAL,
    draft_round     INTEGER,
    draft_pick      INTEGER,
    team            TEXT,
    tier            TEXT DEFAULT 'starter',
    summary         TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, player_name)
);

CREATE INDEX IF NOT EXISTS idx_rookie_watchlist_season_pos
    ON rookie_watchlist(season, position, rank_in_position);

CREATE TABLE IF NOT EXISTS rookie_content_items (
    content_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    season          INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT,
    source          TEXT,
    author          TEXT,
    published_at    TEXT,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary         TEXT,
    body_excerpt    TEXT,
    sentiment       TEXT DEFAULT 'neutral',
    tags            TEXT,
    status          TEXT NOT NULL DEFAULT 'draft',
    FOREIGN KEY (season, player_name) REFERENCES rookie_watchlist(season, player_name)
);

CREATE INDEX IF NOT EXISTS idx_rookie_content_player
    ON rookie_content_items(season, player_name, status);

CREATE TABLE IF NOT EXISTS rookie_expert_signals (
    signal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    season          INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    content_id      INTEGER,
    expert_name     TEXT,
    outlet          TEXT,
    signal_type     TEXT NOT NULL,
    value_json      TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES rookie_content_items(content_id),
    FOREIGN KEY (season, player_name) REFERENCES rookie_watchlist(season, player_name)
);

CREATE INDEX IF NOT EXISTS idx_rookie_signals_player
    ON rookie_expert_signals(season, player_name);
