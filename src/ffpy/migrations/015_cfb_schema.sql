-- FFPy Database Schema — College Football (CFB)
-- Games, rosters, and play-by-play from sportsdataverse / cfbfastR releases.
-- Data source: https://github.com/sportsdataverse/sportsdataverse-data

-- ==================== CFB GAMES ====================
CREATE TABLE IF NOT EXISTS cfb_games (
    game_id             TEXT PRIMARY KEY,
    season              INTEGER NOT NULL,
    week                INTEGER,
    season_type         INTEGER,           -- ESPN: 2=regular, 3=postseason
    game_date           TEXT,
    neutral_site        INTEGER DEFAULT 0,
    conference_game     INTEGER DEFAULT 0,
    home_id             INTEGER,
    away_id             INTEGER,
    home_team           TEXT,
    away_team           TEXT,
    home_abbreviation   TEXT,
    away_abbreviation   TEXT,
    home_score          INTEGER,
    away_score          INTEGER,
    home_winner         INTEGER,
    away_winner         INTEGER,
    venue               TEXT,
    attendance          INTEGER,
    status              TEXT,
    game_finished       INTEGER DEFAULT 0,
    source              TEXT DEFAULT 'espn',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cfb_games_season_week ON cfb_games(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_games_teams ON cfb_games(home_abbreviation, away_abbreviation);
CREATE INDEX IF NOT EXISTS idx_cfb_games_date ON cfb_games(game_date);
CREATE INDEX IF NOT EXISTS idx_cfb_games_season_type ON cfb_games(season, season_type);

-- ==================== CFB ROSTERS ====================
CREATE TABLE IF NOT EXISTS cfb_rosters (
    roster_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    season                  INTEGER NOT NULL,
    team_id                 INTEGER,
    athlete_id              INTEGER NOT NULL,
    athlete_uid             TEXT,
    full_name               TEXT NOT NULL,
    first_name              TEXT,
    last_name               TEXT,
    position_id             TEXT,
    team_abbreviation       TEXT,
    team_name               TEXT,
    team_location           TEXT,
    jersey                  TEXT,
    height                  REAL,
    weight                  REAL,
    age                     REAL,
    date_of_birth           TEXT,
    birth_place_city        TEXT,
    birth_place_state       TEXT,
    experience_years        REAL,
    experience_display_value TEXT,
    status_name             TEXT,
    status_type             TEXT,
    headshot_href           TEXT,
    athlete_href            TEXT,
    active                  INTEGER,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, athlete_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_rosters_season ON cfb_rosters(season);
CREATE INDEX IF NOT EXISTS idx_cfb_rosters_team ON cfb_rosters(team_abbreviation);
CREATE INDEX IF NOT EXISTS idx_cfb_rosters_athlete ON cfb_rosters(athlete_id);
CREATE INDEX IF NOT EXISTS idx_cfb_rosters_name ON cfb_rosters(full_name);

-- ==================== CFB PLAYS ====================
-- Curated play-by-play subset (cfbfastR EPA/WPA + skill-player attribution).
CREATE TABLE IF NOT EXISTS cfb_plays (
    play_id                 TEXT PRIMARY KEY,
    game_id                 TEXT NOT NULL,
    season                  INTEGER NOT NULL,
    week                    INTEGER,
    play_type               TEXT,
    play_text               TEXT,
    period                  INTEGER,
    clock_minutes           INTEGER,
    clock_seconds           INTEGER,
    down                    INTEGER,
    distance                INTEGER,
    yards_to_goal           INTEGER,
    yards_gained            INTEGER,
    pos_team                TEXT,
    def_pos_team            TEXT,
    home_team               TEXT,
    away_team               TEXT,
    passer_player_name      TEXT,
    rusher_player_name      TEXT,
    receiver_player_name    TEXT,
    pass                    INTEGER,
    rush                    INTEGER,
    rush_td                 INTEGER,
    pass_td                 INTEGER,
    interception            INTEGER,
    touchdown               INTEGER,
    epa                     REAL,
    wpa                     REAL,
    wp_before               REAL,
    wp_after                REAL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES cfb_games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_plays_game ON cfb_plays(game_id);
CREATE INDEX IF NOT EXISTS idx_cfb_plays_season_week ON cfb_plays(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_plays_passer ON cfb_plays(passer_player_name);
CREATE INDEX IF NOT EXISTS idx_cfb_plays_rusher ON cfb_plays(rusher_player_name);
CREATE INDEX IF NOT EXISTS idx_cfb_plays_receiver ON cfb_plays(receiver_player_name);
CREATE INDEX IF NOT EXISTS idx_cfb_plays_type ON cfb_plays(play_type);
