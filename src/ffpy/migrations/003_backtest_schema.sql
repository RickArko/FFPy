-- FFPy Database Schema - Backtest Migration
-- Persists results of historical pick'em strategy backtests.
-- Independent of plays schema (003 does not require 002 to have run).

-- ==================== BACKTEST RUNS ====================
-- One row per backtest execution.
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Strategy identification
    strategy_name TEXT NOT NULL,
    strategy_params TEXT,                -- JSON-encoded hyperparameters

    -- Window
    season_start INTEGER NOT NULL,
    season_end INTEGER NOT NULL,
    week_start INTEGER NOT NULL,
    week_end INTEGER NOT NULL,
    season_type TEXT DEFAULT 'REG',      -- REG, POST, PRE

    -- Aggregate metrics
    total_games INTEGER,
    correct INTEGER,
    incorrect INTEGER,
    ties INTEGER,
    confidence_earned INTEGER,
    confidence_max INTEGER,

    -- Notes for the user
    note TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy
    ON backtest_runs(strategy_name, season_start);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_window
    ON backtest_runs(season_start, season_end, season_type);

-- ==================== BACKTEST PICKS ====================
-- One row per pick made during a backtest run.
-- Not foreign-keyed to games (backtest should be robust to DB pruning).
CREATE TABLE IF NOT EXISTS backtest_picks (
    pick_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,

    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_id TEXT NOT NULL,

    selected_team TEXT NOT NULL,
    confidence INTEGER,                  -- NULL for straight-up pools

    -- Outcome: 1 correct, 0 wrong, NULL for tie/not-graded
    correct INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_backtest_picks_run
    ON backtest_picks(run_id, season, week);
CREATE INDEX IF NOT EXISTS idx_backtest_picks_game
    ON backtest_picks(game_id);
