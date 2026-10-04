-- Widen user_credentials.provider to include cbs.
-- SQLite cannot ALTER a CHECK. Applied by
-- FFPyDatabase._upgrade_user_credentials_provider_check, which runs this
-- script only while the live CHECK still omits cbs. Do not executescript
-- this on every startup.

CREATE TABLE user_credentials_cbs (
    cred_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    provider   TEXT NOT NULL CHECK(provider IN ('espn','yahoo','sleeper','cbs')),
    encrypted  TEXT NOT NULL,
    label      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider)
);

INSERT INTO user_credentials_cbs (cred_id, user_id, provider, encrypted, label, created_at, updated_at)
SELECT cred_id, user_id, provider, encrypted, label, created_at, updated_at
FROM user_credentials;

DROP TABLE user_credentials;

ALTER TABLE user_credentials_cbs RENAME TO user_credentials;
