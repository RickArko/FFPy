-- Short-lived user-scoped feature history (draft/lineup/trades saves).
-- GDPR: hard-delete on account erase; expire via expires_at; cap per feature in app code.

CREATE TABLE IF NOT EXISTS user_feature_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    feature       TEXT NOT NULL,
    league_id     TEXT,
    title         TEXT,
    request_json  TEXT NOT NULL,
    result_json   TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ufa_user_feature
    ON user_feature_artifacts(user_id, feature, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ufa_expires
    ON user_feature_artifacts(expires_at);
