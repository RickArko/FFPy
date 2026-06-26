# FFPy Database Reference

Complete guide to the local SQLite fantasy football database — schema, CLI, data feeds, and visualization.

---

## Quick Reference

| Layer | What | CLI / Make |
|-------|------|------------|
| Core schema | players, actual_stats, projections | auto on `init` |
| Play-by-play | games, plays, ftn_charting, snap_counts | `make db.load` |
| Backtesting | backtest_runs, backtest_picks | auto on `init` |
| Advanced stats | player_advanced_stats | `make db.compute-stats` |
| Next Gen Stats | nextgen_stats | `make db.ngs` |
| Injuries | player_injuries | `make db.injuries` |
| DFS salaries | dfs_salaries | `ffpy-db load-dfs` * |
| ADP | adp | `ffpy-db load-adp` * |
| Depth charts | depth_charts | `ffpy-db load-depth-charts` |
| Quality views | vw_player_weeks, vw_missing_games, vw_duplicate_stats | auto |

*Stub — requires API integration to populate.

---

## Architecture

Every data feed follows the 4-layer stack:

```
Migration SQL → Store method (FFPyDatabase) → Loader class → CLI + Make target
```

The database lives at `~/.ffpy/ffpy.db` by default (configurable via `DATABASE_PATH` in `.env`).

```bash
# Check size & record counts
make db.audit

# Or direct DuckDB query
uv run duckdb ~/.ffpy/ffpy.db -c "SELECT 'plays' AS tbl, COUNT(*) FROM plays UNION ALL SELECT 'games', COUNT(*) FROM games;"
```

---

## Schema — All Tables

### `players`
Core player registry. Populated by `store_actual_stats` / `get_or_create_player`.

| Column | Type | Notes |
|--------|------|-------|
| `player_id` | INTEGER PK | |
| `name` | TEXT | NOT NULL |
| `nfl_id` | TEXT UNIQUE | ESPN / GSIS ID |
| `team` | TEXT | Abbreviation (e.g. `KC`) |
| `position` | TEXT | `QB`, `RB`, `WR`, `TE`, `K`, `DST` |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

### `actual_stats`
Weekly per-player fantasy scoring. One row per (player, season, week).

| Column | Type |
|--------|------|
| `stat_id` | INTEGER PK |
| `player_id` | INTEGER FK → players |
| `season` | INTEGER |
| `week` | INTEGER (1-18) |
| `actual_points` | REAL |
| `passing_yards` / `passing_tds` / `interceptions` | INTEGER / REAL |
| `rushing_yards` / `rushing_tds` | INTEGER / REAL |
| `receiving_yards` / `receiving_tds` / `receptions` | INTEGER / REAL |
| `opponent` | TEXT |
| `home_away` | TEXT |
| `game_date` | DATE |
| `source` | TEXT (espn, nflverse, mock) |

UNIQUE(player_id, season, week).

### `projections`
Projected stats from any source. Same stat columns as actual_stats + `source` + `projected_points`.

UNIQUE(player_id, season, week, source).

### `games`
Game-level metadata from nflverse PBP.

| Column | Type |
|--------|------|
| `game_id` | TEXT PK |
| `season` / `season_type` / `week` | |
| `home_team` / `away_team` | TEXT |
| `home_score` / `away_score` | INTEGER |
| `spread_line` / `total_line` | REAL |
| `roof` / `surface` / `temp` / `wind` | Game conditions |
| `stadium` / `location` | TEXT |
| `game_finished` | INTEGER (0/1) |

### `plays`
Play-by-play data from nflfastR (nflverse). 275+ columns covering EPA/WPA, down-distance, passing/rushing/defensive stats, win probability, penalties, etc. Key columns:

| Category | Columns |
|----------|---------|
| Identity | `play_id` PK, `game_id` FK, `season`, `week` |
| Context | `down`, `ydstogo`, `yardline_100`, `qtr`, `game_seconds_remaining` |
| Play type | `play_type` (pass/run/punt/FG/kickoff), `pass_length`, `run_location` |
| Passing | `passer_player_name`, `receiver_player_name`, `air_yards`, `yards_after_catch` |
| Rushing | `rusher_player_name`, `rushing_yards` |
| Analytics | `epa`, `wpa`, `vegas_wpa`, `success`, `cpoe`, `xyac_*` |
| Scoring | `touchdown`, `pass_touchdown`, `rush_touchdown`, `kick_distance` |
| WP | `wp`, `def_wp`, `home_wp`, `vegas_wp` |

Indexes on: game_id, season+week, passer/rusher/receiver, posteam, play_type.

### `snap_counts`
Player participation (2012+). One row per (game_id, player).

| Column | Type |
|--------|------|
| `snap_id` | INTEGER PK |
| `game_id` | TEXT |
| `player_name` | TEXT |
| `team` / `position` / `opponent` | TEXT |
| `offense_snaps` / `offense_pct` | INTEGER / REAL |
| `defense_snaps` / `defense_pct` | INTEGER / REAL |
| `st_snaps` / `st_pct` | INTEGER / REAL |
| `season` / `week` | INTEGER |

UNIQUE(game_id, player_id).

### `ftn_charting`
Advanced charting data from FTN (2022+). One row per play.

| Column | Type |
|--------|------|
| `charting_id` | INTEGER PK |
| `play_id` | TEXT UNIQUE FK → plays |
| `n_offense_backfield`, `qb_location` | Formation |
| `is_play_action`, `is_screen_pass`, `is_rpo`, `is_trick_play` | INTEGER (0/1) |
| `is_motion`, `is_no_huddle` | INTEGER |
| `read_thrown` | TEXT (first_read / second_read / etc.) |
| `n_blitzers`, `n_pass_rushers` | INTEGER |
| `is_catchable_ball`, `is_drop`, `is_throw_away` | INTEGER |

### `player_id_mapping`
Cross-platform ID mapping (GSIS, PFR, ESPN, Yahoo, Sleeper, Sportradar).

### `data_loads`
Audit log of every data load operation.

| Column | Type |
|--------|------|
| `load_id` | INTEGER PK |
| `load_type` | TEXT (pbp, ftn, snaps, roster, advanced_stats, ngs, injuries) |
| `season` / `week` | INTEGER |
| `status` | TEXT (started / completed / failed) |
| `records_loaded` | INTEGER |
| `duration_seconds` | REAL |

### `backtest_runs` / `backtest_picks`
Persisted pick'em strategy backtest results. See [docs/integration/pickem.md](../integration/pickem.md).

---

## Extended Data Tables

### `player_advanced_stats` (Migration 004)
Derived analytics computed from existing plays + snap_counts + FTN. No external data needed.

| Column | Source |
|--------|--------|
| `player_name`, `team`, `season`, `week` | Key |
| `targets`, `air_yards`, `avg_target_distance` | plays: receiver + air_yards |
| `target_share`, `air_yards_share` | Team totals from plays |
| `yards_after_catch_per_rec` | plays: yac / receptions |
| `deep_targets` | plays where `pass_length = 'deep'` (≥20 air yds) |
| `red_zone_targets` | plays where `yardline_100 ≤ 20` |
| `end_zone_targets` | plays where `yardline_100 ≤ 10` |
| `snap_pct` | snap_counts: offense_pct |
| `first_read_targets` | ftn_charting: `read_thrown = 'first_read'` |

```sql
-- Example: top target shares week 1
SELECT player_name, team, targets, target_share, air_yards_share
FROM player_advanced_stats
WHERE season = 2024 AND week = 1
ORDER BY target_share DESC
LIMIT 10;
```

### `nextgen_stats` (Migration 005)
NFL Next Gen Stats via nflreadpy. Three stat types merged into one table:

| Category | Columns |
|----------|---------|
| Passing (QB) | `avg_time_to_throw`, `avg_completed_air_yards`, `avg_intended_air_yards`, `avg_air_yards_differential`, `aggressiveness`, `completion_percentage_above_expectation` |
| Receiving (WR/TE) | `avg_cushion`, `avg_separation`, `avg_yac`, `avg_expected_yac`, `avg_yac_above_expectation` |
| Rushing (RB) | `expected_rush_yards`, `rush_yards_over_expected`, `rush_yards_over_expected_per_att`, `avg_time_to_los`, `efficiency` |

```sql
-- WR separation leaders
SELECT player_name, team, avg_separation, avg_cushion, avg_yac_above_expectation
FROM nextgen_stats
WHERE position = 'WR' AND season = 2024
ORDER BY avg_separation DESC
LIMIT 10;
```

### `player_injuries` (Migration 006)
Weekly injury reports from nflreadpy.

| Column | Type |
|--------|------|
| `player_name` / `team` / `season` / `week` | Key |
| `practice_status` | Full / Limited / DNP |
| `injury_type` | ankle, hamstring, concussion, etc. |
| `game_status` | Active / Questionable / Doubtful / Out |
| `date_reported` | TEXT |

```sql
-- Questionable or worse for week 7
SELECT player_name, team, injury_type, game_status, practice_status
FROM player_injuries
WHERE season = 2024 AND week = 7
  AND game_status IN ('Questionable', 'Doubtful', 'Out');
```

### `dfs_salaries` (Migration 007)
DFS platform salaries (DraftKings, FanDuel).

| Column | Type |
|--------|------|
| `season` / `week` / `platform` / `player_name` | Key |
| `salary` | INTEGER |
| `position` / `team` / `opponent` | TEXT |

### `adp` (Migration 008)
Average draft position across platforms.

| Column | Type |
|--------|------|
| `player_name` / `platform` / `season` | Key |
| `adp` / `adp_high` / `adp_low` | REAL |
| `draft_date` | TEXT |

### `depth_charts` (Migration 009)
Weekly team depth charts.

| Column | Type |
|--------|------|
| `team` / `season` / `week` / `position` / `depth_spot` | Key |
| `player_name` | TEXT |

---

## Data Quality Views (Migration 010)

### `vw_player_weeks`
One row per player/week — was the player active? What was their snap share and fantasy score?

```sql
SELECT player_name, position, week, actual_points, snap_pct, was_active
FROM vw_player_weeks
WHERE season = 2024 AND position = 'WR'
ORDER BY actual_points DESC
LIMIT 15;
```

### `vw_missing_games`
Games in the schedule with no plays loaded.

```sql
SELECT * FROM vw_missing_games WHERE season = 2024;
```

### `vw_duplicate_stats`
Players with >1 stat row in the same week (data integrity issue).

```sql
SELECT * FROM vw_duplicate_stats;
```

---

## Data Pipeline

### Full ingestion flow

```bash
# 1. Load raw nflverse data
make db.load SEASON=2024

# 2. Compute derived analytics (Phase 1)
make db.compute-stats SEASON=2024

# 3. Load Next Gen Stats (Phase 2A)
make db.ngs SEASON=2024

# 4. Load injuries (Phase 2B)
make db.injuries SEASON=2024

# 5. Collect actual fantasy scoring
make db.stats SEASON=2024

# 6. Load depth charts (nflreadpy, no API key needed)
uv run ffpy-db load-depth-charts --season 2024

# 7. Audit
make db.audit
```

### One-shot for a full season

```bash
make data   # runs make db.prepare → PBP load + stats collection
```

### Mock data (offline dev)

```bash
make data DATA_MODE=mock   # generates realistic fake data
```

---

## CLI Reference

| Subcommand | Description | Key Flags |
|-----------|-------------|-----------|
| `migrate` | Create/upgrade schema | `--db-path` |
| `load` | Load nflverse PBP | `--season N`, `--start-season N`, `--end-season N`, `--no-ftn`, `--no-snaps`, `--validate` |
| `update` | Incremental current-season update | `--db-path` |
| `collect-stats` | Fetch actual fantasy stats | `--season`, `--start-week`, `--end-week`, `--source` (nflverse/espn) |
| `prepare` | Generate all app data | `--season`, `--mock`, `--skip-pbp`, `--skip-stats`, `--refresh-pbp` |
| `compute-stats` | Derived player advanced stats | `--season` |
| `load-ngs` | Next Gen Stats | `--season` |
| `load-injuries` | Injury reports | `--season` |
| `audit` | Data quality checks | `--fix` |
| `load-depth-charts` | Depth charts (nflreadpy) | `--season`, `--week` |
| `load-dfs` | DFS salaries (stub) | `--season`, `--week`, `--platforms` |
| `load-adp` | ADP data (stub) | `--season`, `--platforms` |
| `mock` | Generate mock season data | `--season`, `--weeks` |

All subcommands accept `--db-path` for a custom database location.

---

## Make Targets

```bash
make db.load SEASON=2024          # Load PBP
make db.compute-stats SEASON=2024 # Advanced stats
make db.ngs SEASON=2024           # Next Gen Stats
make db.injuries SEASON=2024      # Injuries
make db.stats SEASON=2024         # Fantasy scoring
make db.audit                     # Health check
make db.depth-chart SEASON=2024   # Depth charts
make db.dfs SEASON=2024 WEEK=1    # DFS (stub)
make db.adp SEASON=2024           # ADP (stub)
make db.mock SEASON=2024          # Mock data
make db.migrate                   # Schema (idempotent)
make db.update                    # Incremental update
```

---

## Query & Visualization

### DuckDB (CLI analytics)

```bash
uv run duckdb ~/.ffpy/ffpy.db
```

```sql
-- WR: target share vs yards-after-catch efficiency
SELECT
  pas.player_name,
  pas.team,
  pas.targets,
  pas.target_share,
  pas.yards_after_catch_per_rec,
  ngs.avg_separation,
  ngs.avg_yac_above_expectation
FROM player_advanced_stats pas
LEFT JOIN nextgen_stats ngs
  ON pas.player_name = ngs.player_name
  AND pas.season = ngs.season
  AND pas.week = ngs.week
WHERE pas.season = 2024 AND pas.week = 1
ORDER BY pas.target_share DESC;
```

### Python (Pandas + Plotly)

```python
from ffpy.database import FFPyDatabase
import plotly.express as px

db = FFPyDatabase()

# Advanced stats as DataFrame
df = db.get_player_advanced_stats("Ja'Marr Chase", season=2024)

# Weekly trend
fig = px.line(df, x="week", y=["targets", "air_yards", "yards_after_catch_per_rec"],
              title="Ja'Marr Chase — Weekly Advanced Stats")
fig.show()
```

### Streamlit

The main app at `src/ffpy/app.py` reads `actual_stats` for projections. Extend it with new pages:

```python
# pages/4_Advanced_Stats.py
import streamlit as st
from ffpy.database import FFPyDatabase

db = FFPyDatabase()
player = st.text_input("Player name", "Justin Jefferson")
df = db.get_player_advanced_stats(player, season=2024)
st.dataframe(df)
```

---

## Database File

```
~/.ffpy/ffpy.db  (default, ~2-200 MB depending on seasons loaded)
```

Custom location:

```bash
# .env
DATABASE_PATH=/mnt/ssd/ffpy.db
```

```bash
# CLI
uv run ffpy-db audit --db-path /mnt/ssd/ffpy.db
```

---

## Updating the Schema

All migrations are **append-only** — never edit a merged migration. To add a new table or view:

1. Create `src/ffpy/migrations/011_<name>.sql`
2. Add the filename to `FFPyDatabase.init_database()` in `database.py`
3. Run `make db.migrate` to apply

Migration files use `CREATE TABLE IF NOT EXISTS` / `CREATE VIEW IF NOT EXISTS` so they are idempotent.
