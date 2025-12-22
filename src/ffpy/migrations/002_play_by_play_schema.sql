-- FFPy Database Schema - Play-by-Play Migration
-- Adds NFL play-level data support via nflverse

-- ==================== GAMES TABLE ====================
-- Game-level metadata (one row per game)
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    old_game_id TEXT UNIQUE,
    season INTEGER NOT NULL,
    season_type TEXT,                  -- REG, POST, PRE
    week INTEGER NOT NULL,
    game_date TEXT,

    -- Teams
    home_team TEXT,
    away_team TEXT,

    -- Final scores
    home_score INTEGER,
    away_score INTEGER,

    -- Game context
    roof TEXT,                         -- outdoors, dome, open, closed
    surface TEXT,                      -- grass, fieldturf, matrixturf, etc.
    temp INTEGER,
    wind INTEGER,

    -- Betting lines
    spread_line REAL,
    total_line REAL,

    -- Stadium info
    location TEXT,
    stadium TEXT,

    -- Status
    game_finished INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_games_season_week ON games(season, week);
CREATE INDEX IF NOT EXISTS idx_games_teams ON games(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_season_type ON games(season, season_type);

-- ==================== PLAYS TABLE ====================
-- Play-by-play data (one row per play)
CREATE TABLE IF NOT EXISTS plays (
    -- Primary identification
    play_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    old_game_id TEXT,

    -- Temporal context
    season INTEGER NOT NULL,
    season_type TEXT,
    week INTEGER NOT NULL,
    game_date TEXT,
    qtr INTEGER,
    quarter_seconds_remaining INTEGER,
    game_seconds_remaining INTEGER,
    half_seconds_remaining INTEGER,
    game_half TEXT,                    -- Half, Overtime
    drive INTEGER,

    -- Teams
    posteam TEXT,                      -- Possession team
    defteam TEXT,                      -- Defense team
    home_team TEXT,
    away_team TEXT,
    side_of_field TEXT,

    -- Down & distance
    down INTEGER,
    ydstogo INTEGER,
    yardline_100 INTEGER,              -- Yards to opponent end zone
    goal_to_go INTEGER,

    -- Play details
    play_type TEXT,                    -- pass, run, punt, field_goal, kickoff, etc.
    yards_gained INTEGER,
    desc TEXT,                         -- Play description

    -- Play characteristics
    shotgun INTEGER,
    no_huddle INTEGER,
    qb_dropback INTEGER,
    qb_scramble INTEGER,
    qb_kneel INTEGER,
    qb_spike INTEGER,
    pass_length TEXT,                  -- short, deep
    pass_location TEXT,                -- left, middle, right
    run_location TEXT,                 -- left, middle, right
    run_gap TEXT,                      -- guard, tackle, end

    -- Advanced analytics (nflfastR specialty)
    epa REAL,                          -- Expected Points Added
    wpa REAL,                          -- Win Probability Added
    vegas_wpa REAL,                    -- Spread-adjusted WPA
    success INTEGER,                   -- Boolean (EPA > 0)
    cpoe REAL,                         -- Completion % over expected

    -- EPA components
    air_epa REAL,
    yac_epa REAL,
    comp_air_epa REAL,
    comp_yac_epa REAL,

    -- WPA components
    air_wpa REAL,
    yac_wpa REAL,
    comp_air_wpa REAL,
    comp_yac_wpa REAL,

    -- Expected values
    xyac_epa REAL,                     -- Expected YAC EPA
    xyac_mean_yardage REAL,
    xyac_median_yardage REAL,
    xyac_success REAL,
    xyac_fd REAL,                      -- Expected first down

    -- Passing stats
    passer_player_id TEXT,
    passer_player_name TEXT,
    passing_yards INTEGER,
    air_yards INTEGER,
    yards_after_catch INTEGER,
    complete_pass INTEGER,
    incomplete_pass INTEGER,
    interception INTEGER,
    qb_hit INTEGER,
    sack INTEGER,

    -- Receiving stats
    receiver_player_id TEXT,
    receiver_player_name TEXT,
    receiving_yards INTEGER,

    -- Rushing stats
    rusher_player_id TEXT,
    rusher_player_name TEXT,
    rushing_yards INTEGER,
    lateral_rushing_yards INTEGER,
    lateral_receiver_player_id TEXT,
    lateral_receiver_player_name TEXT,
    lateral_receiving_yards INTEGER,

    -- Scoring events
    touchdown INTEGER,
    pass_touchdown INTEGER,
    rush_touchdown INTEGER,
    return_touchdown INTEGER,
    td_team TEXT,
    td_player_name TEXT,
    td_player_id TEXT,
    extra_point_result TEXT,
    two_point_conv_result TEXT,
    field_goal_result TEXT,
    kick_distance INTEGER,

    -- Score context
    posteam_score INTEGER,
    defteam_score INTEGER,
    score_differential INTEGER,
    posteam_score_post INTEGER,
    defteam_score_post INTEGER,
    score_differential_post INTEGER,

    -- Win probability
    wp REAL,
    def_wp REAL,
    home_wp REAL,
    away_wp REAL,
    vegas_wp REAL,
    vegas_home_wp REAL,

    -- Timeouts
    posteam_timeouts_remaining INTEGER,
    defteam_timeouts_remaining INTEGER,
    home_timeouts_remaining INTEGER,
    away_timeouts_remaining INTEGER,

    -- Penalties
    penalty INTEGER,
    penalty_team TEXT,
    penalty_player_id TEXT,
    penalty_player_name TEXT,
    penalty_type TEXT,
    penalty_yards INTEGER,

    -- Special teams
    punt_blocked INTEGER,
    first_down_rush INTEGER,
    first_down_pass INTEGER,
    first_down_penalty INTEGER,
    third_down_converted INTEGER,
    third_down_failed INTEGER,
    fourth_down_converted INTEGER,
    fourth_down_failed INTEGER,

    -- Fumbles
    fumble INTEGER,
    fumble_forced INTEGER,
    fumble_not_forced INTEGER,
    fumble_out_of_bounds INTEGER,
    fumble_lost INTEGER,
    fumble_recovery_1_team TEXT,
    fumble_recovery_1_player_id TEXT,
    fumble_recovery_1_player_name TEXT,
    fumble_recovery_1_yards INTEGER,

    -- Safety
    safety INTEGER,

    -- Tacklers
    solo_tackle_1_team TEXT,
    solo_tackle_1_player_id TEXT,
    solo_tackle_1_player_name TEXT,
    solo_tackle_2_team TEXT,
    solo_tackle_2_player_id TEXT,
    solo_tackle_2_player_name TEXT,

    -- Two point conversions
    two_point_attempt INTEGER,

    -- Aborted plays
    aborted_play INTEGER,

    -- Replay
    replay_or_challenge INTEGER,
    replay_or_challenge_result TEXT,

    -- Series info
    series INTEGER,
    series_success INTEGER,
    series_result TEXT,
    order_sequence INTEGER,

    -- Start/End field position
    start_time TEXT,
    time_of_day TEXT,
    stadium TEXT,
    weather TEXT,
    nfl_api_id TEXT,
    play_clock TEXT,

    -- Flags
    play_deleted INTEGER,
    play_type_nfl TEXT,
    special_teams_play INTEGER,
    st_play_type TEXT,
    end_clock_time TEXT,
    end_yard_line TEXT,
    fixed_drive INTEGER,
    fixed_drive_result TEXT,
    drive_real_start_time TEXT,
    drive_play_count INTEGER,
    drive_time_of_possession TEXT,
    drive_first_downs INTEGER,
    drive_inside20 INTEGER,
    drive_ended_with_score INTEGER,
    drive_quarter_start INTEGER,
    drive_quarter_end INTEGER,
    drive_yards_penalized INTEGER,
    drive_start_transition TEXT,
    drive_end_transition TEXT,
    drive_game_clock_start TEXT,
    drive_game_clock_end TEXT,
    drive_start_yard_line TEXT,
    drive_end_yard_line TEXT,
    drive_play_id_started TEXT,
    drive_play_id_ended TEXT,

    -- Out of bounds
    out_of_bounds INTEGER,

    -- Tackle for loss
    tackled_for_loss INTEGER,

    -- QB data
    qb_epa REAL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

-- Performance indexes for plays table
CREATE INDEX IF NOT EXISTS idx_plays_game ON plays(game_id);
CREATE INDEX IF NOT EXISTS idx_plays_season_week ON plays(season, week);
CREATE INDEX IF NOT EXISTS idx_plays_season_type ON plays(season, season_type);
CREATE INDEX IF NOT EXISTS idx_plays_passer ON plays(passer_player_id);
CREATE INDEX IF NOT EXISTS idx_plays_rusher ON plays(rusher_player_id);
CREATE INDEX IF NOT EXISTS idx_plays_receiver ON plays(receiver_player_id);
CREATE INDEX IF NOT EXISTS idx_plays_posteam ON plays(posteam);
CREATE INDEX IF NOT EXISTS idx_plays_defteam ON plays(defteam);
CREATE INDEX IF NOT EXISTS idx_plays_type ON plays(play_type);
CREATE INDEX IF NOT EXISTS idx_plays_down ON plays(down);
CREATE INDEX IF NOT EXISTS idx_plays_drive ON plays(game_id, drive);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_plays_player_season ON plays(passer_player_name, rusher_player_name, receiver_player_name, season);
CREATE INDEX IF NOT EXISTS idx_plays_team_season ON plays(posteam, season, week);

-- ==================== FTN CHARTING TABLE ====================
-- Advanced charting data from FTN (2022+ seasons only)
CREATE TABLE IF NOT EXISTS ftn_charting (
    charting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    play_id TEXT UNIQUE NOT NULL,

    -- Formation & personnel
    n_offense_backfield INTEGER,       -- Number of players in backfield at snap
    qb_location TEXT,                  -- under_center, shotgun, pistol

    -- Play characteristics
    is_play_action INTEGER,            -- Boolean
    is_screen_pass INTEGER,
    is_rpo INTEGER,                    -- Run-pass option
    is_trick_play INTEGER,
    is_qb_sneak INTEGER,
    is_motion INTEGER,
    is_no_huddle INTEGER,
    is_qb_out_of_pocket INTEGER,

    -- Pass details
    is_catchable_ball INTEGER,
    is_contested_ball INTEGER,
    is_created_reception INTEGER,      -- Exceptional receiver play
    is_drop INTEGER,
    is_throw_away INTEGER,
    is_interception_worthy INTEGER,
    read_thrown TEXT,                  -- first_read, second_read, third_read, etc.

    -- Defense
    n_blitzers INTEGER,
    n_pass_rushers INTEGER,
    is_qb_fault_sack INTEGER,

    -- Other details
    starting_hash TEXT,                -- left, middle, right

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (play_id) REFERENCES plays(play_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ftn_play ON ftn_charting(play_id);
CREATE INDEX IF NOT EXISTS idx_ftn_play_action ON ftn_charting(is_play_action);
CREATE INDEX IF NOT EXISTS idx_ftn_rpo ON ftn_charting(is_rpo);

-- ==================== SNAP COUNTS TABLE ====================
-- Player participation data (2012+ seasons)
CREATE TABLE IF NOT EXISTS snap_counts (
    snap_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    pfr_game_id TEXT,
    player_id TEXT NOT NULL,
    pfr_player_id TEXT,
    player_name TEXT NOT NULL,
    team TEXT NOT NULL,
    position TEXT NOT NULL,

    -- Snap counts
    offense_snaps INTEGER DEFAULT 0,
    offense_pct REAL DEFAULT 0.0,
    defense_snaps INTEGER DEFAULT 0,
    defense_pct REAL DEFAULT 0.0,
    st_snaps INTEGER DEFAULT 0,        -- Special teams
    st_pct REAL DEFAULT 0.0,

    -- Context
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    opponent TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_snaps_player ON snap_counts(player_id, season);
CREATE INDEX IF NOT EXISTS idx_snaps_player_name ON snap_counts(player_name, season);
CREATE INDEX IF NOT EXISTS idx_snaps_game ON snap_counts(game_id);
CREATE INDEX IF NOT EXISTS idx_snaps_team ON snap_counts(team, season, week);

-- ==================== PLAYER ID MAPPING ====================
-- Map between different player ID systems
CREATE TABLE IF NOT EXISTS player_id_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Our internal ID
    ffpy_player_id INTEGER,

    -- nflverse IDs
    gsis_id TEXT UNIQUE,               -- NFL GSIS ID (primary in nflverse)
    pfr_id TEXT,                       -- Pro Football Reference ID
    espn_id TEXT,                      -- ESPN ID
    yahoo_id TEXT,                     -- Yahoo ID
    sleeper_id TEXT,                   -- Sleeper ID
    sportradar_id TEXT,                -- Sportradar ID
    fantasypros_id TEXT,               -- FantasyPros ID

    -- Player info
    player_name TEXT,
    position TEXT,
    team TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ffpy_player_id) REFERENCES players(player_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_player_mapping_gsis ON player_id_mapping(gsis_id);
CREATE INDEX IF NOT EXISTS idx_player_mapping_ffpy ON player_id_mapping(ffpy_player_id);
CREATE INDEX IF NOT EXISTS idx_player_mapping_name ON player_id_mapping(player_name);

-- ==================== DATA LOAD TRACKING ====================
-- Track data loads and updates
CREATE TABLE IF NOT EXISTS data_loads (
    load_id INTEGER PRIMARY KEY AUTOINCREMENT,

    load_type TEXT NOT NULL,           -- pbp, ftn, snaps, roster
    season INTEGER NOT NULL,
    week INTEGER,                      -- NULL for full season loads

    status TEXT NOT NULL,              -- started, completed, failed
    records_loaded INTEGER DEFAULT 0,
    error_message TEXT,

    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_data_loads_season ON data_loads(load_type, season, status);
CREATE INDEX IF NOT EXISTS idx_data_loads_status ON data_loads(status, started_at);
