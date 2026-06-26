-- FFPy Database Schema - Game Weather Migration
-- Per-game weather conditions extracted from nflverse play-by-play data.
-- Separate from the games table to allow richer weather data without schema drift.

CREATE TABLE IF NOT EXISTS game_weather (
    weather_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL UNIQUE,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,

    -- Core weather
    temp INTEGER,                        -- Temperature (°F)
    wind INTEGER,                        -- Wind speed (mph)
    humidity INTEGER,                    -- Humidity percentage
    precip REAL,                         -- Precipitation (inches, where available)

    -- Conditions
    weather_condition TEXT,              -- Parsed condition (Clear, Cloudy, Rain, Snow, etc.)
    roof TEXT,                           -- outdoors, dome, open, closed
    surface TEXT,                        -- grass, fieldturf, etc.

    -- Raw text from nflverse PBP
    weather_description TEXT,            -- e.g. "Cloudy Temp: 40° F, Humidity: 72%, Wind: 6mph"

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_game_weather_season
    ON game_weather(season);
CREATE INDEX IF NOT EXISTS idx_game_weather_condition
    ON game_weather(weather_condition);
