-- FFPy Database Schema — Player Rosters & Bios
-- Adds seasonal player roster data from nflreadpy.
-- Each row represents a player's profile for a given season,
-- enabling age-curve regression, rookie draft-capital priors,
-- and physical-profile-based comps.

CREATE TABLE IF NOT EXISTS player_rosters (
    roster_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    gsis_id         TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    team            TEXT,
    season          INTEGER NOT NULL,
    age             INTEGER,
    height          INTEGER,        -- in inches
    weight          INTEGER,        -- in lbs
    years_exp       INTEGER,
    college         TEXT,
    draft_round     INTEGER,
    draft_pick      INTEGER,
    draft_team      TEXT,
    status          TEXT,           -- ACT, Reserve, etc.
    headshot_url    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(gsis_id, season)
);

CREATE INDEX IF NOT EXISTS idx_player_rosters_gsis    ON player_rosters(gsis_id);
CREATE INDEX IF NOT EXISTS idx_player_rosters_season  ON player_rosters(season);
CREATE INDEX IF NOT EXISTS idx_player_rosters_team    ON player_rosters(team);
CREATE INDEX IF NOT EXISTS idx_player_rosters_pos     ON player_rosters(position);
