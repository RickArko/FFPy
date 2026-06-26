-- FFPy Database Schema - Data Quality Views Migration
-- Read-only views for health-checking the database.

CREATE VIEW IF NOT EXISTS vw_player_weeks AS
SELECT
    p.name AS player_name,
    p.position,
    p.team,
    a.season,
    a.week,
    a.actual_points,
    CASE WHEN a.actual_points IS NOT NULL THEN 1 ELSE 0 END AS was_active,
    COALESCE(sc.offense_snaps, 0) AS offense_snaps,
    COALESCE(sc.offense_pct, 0.0) AS snap_pct
FROM players p
LEFT JOIN actual_stats a ON p.player_id = a.player_id
LEFT JOIN snap_counts sc
    ON sc.player_name = p.name
    AND sc.season = a.season
    AND sc.week = a.week;

CREATE VIEW IF NOT EXISTS vw_missing_games AS
SELECT
    g.season,
    g.week,
    g.game_id,
    g.home_team,
    g.away_team,
    g.game_date
FROM games g
LEFT JOIN plays p ON g.game_id = p.game_id
WHERE p.play_id IS NULL;

CREATE VIEW IF NOT EXISTS vw_duplicate_stats AS
SELECT
    player_id,
    season,
    week,
    COUNT(*) AS row_count
FROM actual_stats
GROUP BY player_id, season, week
HAVING COUNT(*) > 1;
