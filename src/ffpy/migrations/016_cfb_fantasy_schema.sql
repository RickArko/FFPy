-- FFPy Database Schema — College Fantasy Football (SEC / Big Ten / ACC MVP)
-- Extends 015_cfb_schema with teams, player stats, fantasy points, projections, and league tables.

-- ==================== ALTER EXISTING CFB TABLES ====================
-- SQLite does not support IF NOT EXISTS on ADD COLUMN; use separate migration-safe approach.
-- New installs get columns via CREATE in 015 if we re-run; for upgrades we add via init script.
-- These ALTERs are idempotent only when wrapped by application logic; here we document target columns.
-- Application init_database runs this file once; ALTER failures on missing parent are avoided by
-- storing extended game/roster fields only in new tables where possible.

-- ==================== CFB TEAMS ====================
CREATE TABLE IF NOT EXISTS cfb_teams (
    team_key        TEXT NOT NULL,
    season          INTEGER NOT NULL,
    cfbd_team       TEXT,
    espn_team_id    INTEGER,
    abbreviation    TEXT,
    school          TEXT NOT NULL,
    conference      TEXT NOT NULL,
    division        TEXT,
    classification  TEXT,
    color           TEXT,
    alt_color       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_key, season)
);

CREATE INDEX IF NOT EXISTS idx_cfb_teams_season_conf ON cfb_teams(season, conference);
CREATE INDEX IF NOT EXISTS idx_cfb_teams_cfbd ON cfb_teams(cfbd_team, season);

-- ==================== CFB ID MAP (ESPN <-> CFBD) ====================
CREATE TABLE IF NOT EXISTS cfb_id_map (
    map_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season              INTEGER NOT NULL,
    espn_athlete_id     INTEGER,
    cfbd_athlete_id     INTEGER,
    full_name           TEXT NOT NULL,
    team_key            TEXT,
    match_method        TEXT,
    confidence          REAL DEFAULT 1.0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, espn_athlete_id, cfbd_athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_id_map_espn ON cfb_id_map(season, espn_athlete_id);
CREATE INDEX IF NOT EXISTS idx_cfb_id_map_cfbd ON cfb_id_map(season, cfbd_athlete_id);

-- ==================== CFB PLAYERS (canonical registry) ====================
CREATE TABLE IF NOT EXISTS cfb_players (
    player_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    season              INTEGER NOT NULL,
    full_name           TEXT NOT NULL,
    position            TEXT,
    team_key            TEXT,
    conference          TEXT,
    cfbd_athlete_id     INTEGER,
    espn_athlete_id     INTEGER,
    jersey              TEXT,
    conference_eligible INTEGER DEFAULT 1,
    fantasy_eligible    INTEGER DEFAULT 1,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, cfbd_athlete_id),
    UNIQUE(season, espn_athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_players_season_team ON cfb_players(season, team_key);
CREATE INDEX IF NOT EXISTS idx_cfb_players_season_conf ON cfb_players(season, conference);
CREATE INDEX IF NOT EXISTS idx_cfb_players_position ON cfb_players(season, position);

-- ==================== CFB PLAYER GAME STATS ====================
CREATE TABLE IF NOT EXISTS cfb_player_game_stats (
    stat_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cfbd_athlete_id         INTEGER NOT NULL,
    cfbd_game_id            INTEGER NOT NULL,
    player_id               INTEGER,
    season                  INTEGER NOT NULL,
    week                    INTEGER,
    team_key                TEXT,
    opponent_team_key       TEXT,
    opponent_classification TEXT,
    category                TEXT,
    passing_yards           REAL DEFAULT 0,
    passing_tds             REAL DEFAULT 0,
    passing_interceptions   REAL DEFAULT 0,
    passing_completions     REAL DEFAULT 0,
    passing_attempts        REAL DEFAULT 0,
    rushing_yards           REAL DEFAULT 0,
    rushing_tds             REAL DEFAULT 0,
    rushing_attempts        REAL DEFAULT 0,
    receiving_yards         REAL DEFAULT 0,
    receiving_tds           REAL DEFAULT 0,
    receptions              REAL DEFAULT 0,
    fumbles_lost            REAL DEFAULT 0,
    field_goals_made        REAL DEFAULT 0,
    field_goals_attempts    REAL DEFAULT 0,
    extra_points_made       REAL DEFAULT 0,
    extra_points_attempts   REAL DEFAULT 0,
    stat_json               TEXT,
    source                  TEXT DEFAULT 'cfbd',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cfbd_athlete_id, cfbd_game_id, category)
);

CREATE INDEX IF NOT EXISTS idx_cfb_pgs_season_week ON cfb_player_game_stats(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_pgs_player ON cfb_player_game_stats(player_id, season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_pgs_cfbd_athlete ON cfb_player_game_stats(cfbd_athlete_id, season);

-- ==================== CFB TEAM DEFENSE STATS ====================
CREATE TABLE IF NOT EXISTS cfb_team_defense_stats (
    def_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    team_key            TEXT NOT NULL,
    cfbd_game_id        INTEGER NOT NULL,
    season              INTEGER NOT NULL,
    week                INTEGER,
    opponent_team_key   TEXT,
    sacks               REAL DEFAULT 0,
    interceptions       REAL DEFAULT 0,
    fumbles_recovered   REAL DEFAULT 0,
    defensive_tds       REAL DEFAULT 0,
    safeties            REAL DEFAULT 0,
    points_allowed      REAL DEFAULT 0,
    yards_allowed       REAL DEFAULT 0,
    stat_json           TEXT,
    source              TEXT DEFAULT 'cfbd',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_key, cfbd_game_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_tds_season_week ON cfb_team_defense_stats(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_tds_team ON cfb_team_defense_stats(team_key, season);

-- ==================== CFB FANTASY POINTS ====================
CREATE TABLE IF NOT EXISTS cfb_fantasy_points (
    fp_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id               INTEGER NOT NULL,
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    scoring_preset          TEXT NOT NULL DEFAULT 'college_standard',
    actual_points           REAL NOT NULL,
    passing_yards           REAL DEFAULT 0,
    passing_tds             REAL DEFAULT 0,
    interceptions           REAL DEFAULT 0,
    rushing_yards           REAL DEFAULT 0,
    rushing_tds             REAL DEFAULT 0,
    receiving_yards         REAL DEFAULT 0,
    receiving_tds           REAL DEFAULT 0,
    receptions              REAL DEFAULT 0,
    fumbles_lost            REAL DEFAULT 0,
    field_goals_made        REAL DEFAULT 0,
    extra_points_made       REAL DEFAULT 0,
    opponent_classification TEXT,
    fcs_discount_applied    INTEGER DEFAULT 0,
    conference_eligible     INTEGER DEFAULT 1,
    team_key                TEXT,
    opponent_team_key       TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, season, week, scoring_preset)
);

CREATE INDEX IF NOT EXISTS idx_cfb_fp_season_week ON cfb_fantasy_points(season, week);
CREATE INDEX IF NOT EXISTS idx_cfb_fp_player ON cfb_fantasy_points(player_id, season);

-- ==================== CFB PROJECTIONS ====================
CREATE TABLE IF NOT EXISTS cfb_projections (
    projection_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL,
    season              INTEGER NOT NULL,
    week                INTEGER NOT NULL,
    model               TEXT NOT NULL DEFAULT 'historical',
    projected_points    REAL NOT NULL,
    passing_yards       REAL DEFAULT 0,
    passing_tds         REAL DEFAULT 0,
    interceptions       REAL DEFAULT 0,
    rushing_yards       REAL DEFAULT 0,
    rushing_tds         REAL DEFAULT 0,
    receiving_yards     REAL DEFAULT 0,
    receiving_tds       REAL DEFAULT 0,
    receptions          REAL DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, season, week, model)
);

CREATE INDEX IF NOT EXISTS idx_cfb_proj_season_week ON cfb_projections(season, week);

-- ==================== CFB LEAGUES (hosted MVP) ====================
CREATE TABLE IF NOT EXISTS cfb_leagues (
    league_id           TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    name                TEXT NOT NULL,
    season              INTEGER NOT NULL,
    allowed_conferences TEXT NOT NULL,
    scoring_json        TEXT NOT NULL,
    roster_slots_json   TEXT NOT NULL,
    num_teams           INTEGER DEFAULT 10,
    playoff_weeks       TEXT,
    fcs_discount_pct    REAL DEFAULT 0.75,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cfb_leagues_user ON cfb_leagues(user_id);

CREATE TABLE IF NOT EXISTS cfb_league_teams (
    league_team_id      TEXT PRIMARY KEY,
    league_id           TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    team_name           TEXT NOT NULL,
    owner_name          TEXT,
    wins                INTEGER DEFAULT 0,
    losses              INTEGER DEFAULT 0,
    ties                INTEGER DEFAULT 0,
    points_for          REAL DEFAULT 0,
    points_against      REAL DEFAULT 0,
    faab_budget         REAL DEFAULT 100,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cfb_league_teams_league ON cfb_league_teams(league_id);

CREATE TABLE IF NOT EXISTS cfb_league_rosters (
    roster_entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    league_team_id      TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id) ON DELETE CASCADE,
    player_id           INTEGER NOT NULL,
    slot                TEXT DEFAULT 'BENCH',
    acquired_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_team_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_league_rosters_team ON cfb_league_rosters(league_team_id);

CREATE TABLE IF NOT EXISTS cfb_lineups (
    lineup_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    league_team_id      TEXT NOT NULL REFERENCES cfb_league_teams(league_team_id) ON DELETE CASCADE,
    season              INTEGER NOT NULL,
    week                INTEGER NOT NULL,
    player_id           INTEGER NOT NULL,
    slot                TEXT NOT NULL,
    is_starter          INTEGER DEFAULT 1,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_team_id, season, week, player_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_lineups_team_week ON cfb_lineups(league_team_id, season, week);

CREATE TABLE IF NOT EXISTS cfb_matchups (
    matchup_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id           TEXT NOT NULL REFERENCES cfb_leagues(league_id) ON DELETE CASCADE,
    season              INTEGER NOT NULL,
    week                INTEGER NOT NULL,
    home_team_id        TEXT NOT NULL,
    away_team_id        TEXT NOT NULL,
    home_score          REAL,
    away_score          REAL,
    is_playoff          INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_id, season, week, home_team_id, away_team_id)
);

CREATE INDEX IF NOT EXISTS idx_cfb_matchups_league_week ON cfb_matchups(league_id, season, week);

-- ==================== EXTENDED CFB GAME METADATA ====================
CREATE TABLE IF NOT EXISTS cfb_game_meta (
    game_id                 TEXT PRIMARY KEY,
    cfbd_game_id            INTEGER,
    home_conference         TEXT,
    away_conference         TEXT,
    home_classification     TEXT,
    away_classification     TEXT,
    home_team_key           TEXT,
    away_team_key           TEXT,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================== EXTENDED ROSTER FIELDS ====================
CREATE TABLE IF NOT EXISTS cfb_roster_meta (
    roster_id           INTEGER PRIMARY KEY,
    position            TEXT,
    cfbd_athlete_id     INTEGER,
    team_key            TEXT,
    FOREIGN KEY (roster_id) REFERENCES cfb_rosters(roster_id) ON DELETE CASCADE
);

-- ==================== VIEWS ====================
CREATE VIEW IF NOT EXISTS vw_cfb_eligible_players AS
SELECT
    p.player_id,
    p.season,
    p.full_name,
    p.position,
    p.team_key,
    p.conference,
    p.cfbd_athlete_id,
    p.espn_athlete_id,
    t.school AS team_name,
    t.abbreviation AS team_abbreviation
FROM cfb_players p
LEFT JOIN cfb_teams t ON p.team_key = t.team_key AND p.season = t.season
WHERE p.conference_eligible = 1
  AND p.fantasy_eligible = 1
  AND p.position IN ('QB', 'RB', 'WR', 'TE', 'K', 'DST');

CREATE VIEW IF NOT EXISTS vw_cfb_player_weeks AS
SELECT
    fp.player_id,
    p.full_name,
    p.position,
    p.team_key,
    p.conference,
    fp.season,
    fp.week,
    fp.actual_points,
    fp.scoring_preset,
    fp.conference_eligible,
    fp.opponent_classification,
    fp.fcs_discount_applied,
    fp.passing_yards,
    fp.rushing_yards,
    fp.receiving_yards,
    fp.receptions,
    fp.opponent_team_key
FROM cfb_fantasy_points fp
JOIN cfb_players p ON fp.player_id = p.player_id AND fp.season = p.season;
