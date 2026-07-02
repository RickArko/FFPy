# Quick Start

Three commands get you running with database-backed app data. Works on Linux, macOS, and Windows (via WSL).

## First-time setup

```bash
make bootstrap
```

This installs `uv`, syncs Python dependencies, seeds `.env` from the template, and creates the SQLite database. Safe to re-run any time.

## Generate app data

```bash
make data
```

This prepares the SQLite schema, loads nflverse play-by-play/game data, and collects nflverse player actual stats for the default season. For a fast offline demo dataset, run `make data DATA_MODE=mock`.

## Run the app

```bash
make run
```

The Streamlit app opens at `http://localhost:8501`. Stop with `Ctrl+C`.

## Common next steps

| You want to…                        | Run                                   |
|-------------------------------------|---------------------------------------|
| Generate all required app data      | `make data`                           |
| Generate offline demo app data      | `make data DATA_MODE=mock`            |
| Load a real NFL season              | `make db.load SEASON=2024`            |
| Top up the current season weekly    | `make db.update`                      |
| Populate a realistic mock season    | `make db.mock SEASON=2024`            |
| Pull actual player stats            | `make db.stats SEASON=2024`           |
| Dev mode (auto-reload on save)      | `make dev`                            |
| Run the test suite                  | `make test`                           |
| Launch Jupyter for EDA              | `make notebook`                       |
| Load college fantasy data (SEC/B1G/ACC) | `make cfb-full-data SEASON=2024` |
| Explore college data in notebook  | `notebooks/cfb/00_college_fantasy_starter.ipynb` |
| See every target with a description | `make help`                           |

All database targets are thin wrappers over the `ffpy-db` CLI — run `uv run ffpy-db --help` for the full surface.

## College fantasy database (SEC / Big Ten / ACC)

FFPy can load a full college fantasy dataset into the same SQLite database used for NFL — teams, player game stats, fantasy points, and projections scoped to **SEC, Big Ten, and ACC**.

### 1. Get a CFBD API key

Player game stats and team defense come from [CollegeFootballData.com](https://collegefootballdata.com). Request a free key at [collegefootballdata.com/key](https://collegefootballdata.com/key) (emailed to you, no credit card).

Add it to `.env`:

```bash
CFBD_API_KEY=your_actual_key_here
```

### 2. Run the full pipeline

From the repo root (after `make bootstrap`):

```bash
make cfb-full-data SEASON=2024
```

This runs, in order:

| Step | What it loads |
|------|----------------|
| Teams | `cfb_teams` — conference membership (CFBD, ESPN fallback) |
| Games | `cfb_games` — schedules (ESPN parquet / PBP) |
| Rosters | `cfb_rosters` — when upstream parquet exists |
| Stats | `cfb_player_game_stats`, `cfb_team_defense_stats` (CFBD) |
| Players | `cfb_players`, `cfb_id_map` — ESPN↔CFBD crosswalk |
| Fantasy | `cfb_fantasy_points` — `college_standard` scoring + FCS discount |
| Projections | `cfb_projections` — rolling historical model |
| Audit | Row counts and coverage summary |

Default conferences: `SEC,Big Ten,ACC`. Override with:

```bash
make cfb-full-data SEASON=2024 CFB_CONFERENCES="SEC,Big Ten,ACC"
```

### 3. Step-by-step (optional)

```bash
make db.cfb-teams SEASON=2024
make db.cfb SEASON=2024              # games; add CFB_PBP=1 for play-by-play
make db.cfb-rosters SEASON=2024      # skip if season not published yet
make db.cfb-stats SEASON=2024        # requires CFBD_API_KEY
make db.cfb-players SEASON=2024
make db.cfb-fantasy SEASON=2024
make db.cfb-projections SEASON=2024 WEEK=5
make db.audit-cfb SEASON=2024
```

### 4. Explore in Jupyter

```bash
make notebook
```

Open **`notebooks/cfb/00_college_fantasy_starter.ipynb`** — a starter exploration (teams, weekly leaders, FCS discount, projections) inspired by the [CFBD Starter Pack](https://collegefootballdata.gumroad.com/l/starter-pack), but querying your local FFPy database instead of raw API calls.

### 5. League API (optional)

After data is loaded, hosted college leagues are available at `/api/cfb/*` when running the web app:

```bash
make pickem-web
```

Create leagues, set lineups, and score weeks against `cfb_fantasy_points`.

### College troubleshooting

| Issue | Fix |
|-------|-----|
| `CFBD_API_KEY is required` | Set key in `.env` (see step 1) |
| 2025 rosters missing | ESPN rosters lag upstream — games still load; use `--skip-rosters` or `SEASON=2024` for full stats |
| Rate limits on CFBD | Run step-by-step targets; stats load by week + conference |
| Empty fantasy points | Run `make db.cfb-stats` then `make db.cfb-players` before `make db.cfb-fantasy` |

## Windows note

Run all commands from **WSL** (Ubuntu recommended). `make` and `bash` need to be in your shell. The native `cmd.exe` / PowerShell path is intentionally unsupported so there's exactly one blessed flow to maintain.

## Troubleshooting

- **`command not found: uv` right after bootstrap** — open a new shell, or `source ~/.local/bin/env`, then re-run `make bootstrap`.
- **Port 8501 already in use** — `make run PORT=8502`.
- **Browser doesn't open** — navigate to `http://localhost:8501` manually.
- **Need API keys** — edit `.env` (see `.env.example` for the list).
