-- Sleeper profile linking (Supabase user ↔ Sleeper account)
CREATE TABLE IF NOT EXISTS user_sleeper_profiles (
    user_id TEXT PRIMARY KEY,
    sleeper_user_id TEXT NOT NULL,
    sleeper_username TEXT NOT NULL,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sleeper_profiles_sleeper_user ON user_sleeper_profiles(sleeper_user_id);

-- Multi-year franchise grouping via Sleeper previous_league_id chains
CREATE TABLE IF NOT EXISTS league_franchises (
    franchise_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    canonical_sleeper_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_league_franchises_user ON league_franchises(user_id);
