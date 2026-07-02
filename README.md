# FFPy - Fantasy Football Python

A Streamlit app and Python toolkit for fantasy football projections, lineup optimization, play-by-play analytics, and pick'em backtesting. Pulls data from [nflverse](https://nflverse.github.io/), ESPN, or SportsDataIO and runs everything locally against a SQLite database.

**Live app:** [ffpy-pickem.fly.dev](https://ffpy-pickem.fly.dev/) — [League Manager](https://ffpy-pickem.fly.dev/league/) · [Pick'em Tester](https://ffpy-pickem.fly.dev/pickem/)

![Project Logo](docs/assets/static/FFPy.png)

---

## Quick start

```bash
make bootstrap           # one-time: uv, deps, .env, DB schema
make full-data SEASON=2024  # loads everything: PBP → stats → advanced stats → NGS → injuries → depth charts → audit
make run                 # starts Streamlit on http://localhost:8501
```

See [QUICKSTART.md](QUICKSTART.md) for the two-minute walkthrough.

### Step-by-step happy path

If you prefer to run each stage individually:

```bash
make bootstrap              # one-time setup
make db.load SEASON=2024    # 1. nflverse play-by-play + games + FTN + snaps
make db.compute-stats       # 2. derived analytics (target share, routes, red zone)
make db.ngs                 # 3. Next Gen Stats (QB passing / WR separation / RB efficiency)
make db.injuries            # 4. injury reports (practice status, game status)
uv run ffpy-db load-depth-charts --season 2024  # 5. weekly depth charts
make db.stats               # 6. per-player fantasy scoring
make db.audit               # 7. health check — row counts, missing games, duplicates
make run                    # 8. launch Streamlit at http://localhost:8501
```

**Note on audit output**: `make db.audit` exits with code 1 when issues like missing games or
duplicates are found as a CI hygiene signal. The `full-data` target treats it as informational
and continues. Missing games (e.g., `vw_missing_games`) are expected when you've only loaded
partial season data — they fill in as more weeks get loaded.

## Make targets

`make help` lists everything. Key targets:

| Target                        | What it does                                         |
|-------------------------------|------------------------------------------------------|
| `make bootstrap`              | First-time setup (idempotent)                        |
| `make data`                   | PBP + stats (legacy; prefer `full-data` or stepwise) |
| `make full-data SEASON=2024`  | **Full pipeline**: PBP → stats → advanced stats → NGS → injuries → depth charts → audit |
| `make run` / `make dev`       | Launch Streamlit (dev = auto-reload on save)         |
| `make pickem-web PORT=8000`   | Launch the FastAPI + Vue pick'em strategy tester     |
| `make test` / `make cov`      | Pytest, optionally with coverage                     |
| `make lint` / `make fmt`      | Ruff lint / format                                   |
| `make check`                  | `lint` + `test` (CI entry point)                     |
| `make notebook`               | Jupyter Lab with analysis deps                       |

### Database pipeline (run in order)

| Target                        | What it does                                         |
|-------------------------------|------------------------------------------------------|
| `make db.load SEASON=2024`    | Load nflverse play-by-play + games + FTN + snaps     |
| `make db.compute-stats`       | Derived analytics: targets, routes, red-zone usage   |
| `make db.ngs`                 | Next Gen Stats (passing / receiving / rushing)       |
| `make db.injuries`            | Injury reports (practice/game status per week)       |
| `make db.depth-chart`         | Weekly team depth charts (via nflreadpy)             |
| `make db.stats`               | Collect actual fantasy scoring per player-week       |
| `make db.audit`               | Health check — missing games, duplicates, row counts |

Phase 3 stubs (require API integration): `db.dfs`, `db.adp`.

All database targets wrap the `ffpy-db` CLI — `uv run ffpy-db --help` for the full surface.

## Configuration

Copy and edit `.env`:

```bash
cp .env.example .env
```

Key settings: `API_PROVIDER` (espn/sportsdata), `NFL_SEASON`, `DATABASE_PATH`.

## Features

- Streamlit app: projections, player comparison, pick'em analyzer
- FastAPI + Vue pick'em strategy tester with Supabase auth
- Lineup optimizer (PuLP/CBC) for PPR / Half-PPR / Standard, superflex, custom rosters
- Historical projection model (weighted recent performance)
- ESPN + SportsDataIO integrations with automatic fallback
- Local SQLite with nflverse play-by-play, FTN charting, and snap counts
- **Derived advanced stats**: target share, air yards share, deep / red-zone / end-zone targets, routes, snap %, first-read targets
- **Next Gen Stats**: QB time-to-throw / CPOE, WR separation / cushion / YAC over expected, RB efficiency / rush yards over expected
- **Injury tracking**: weekly practice status, injury type, game status across all players
- **Depth charts**: weekly team depth charts via nflreadpy
- **Data quality views**: `vw_player_weeks`, `vw_missing_games`, `vw_duplicate_stats`
- **Audit CLI**: `ffpy-db audit` — row counts, missing games, duplicates, view health

## Deployment

Production Dockerfile + `fly.toml` in repo. CI builds and deploys to Fly.io on `main` push.

- **Live:** [https://ffpy-pickem.fly.dev](https://ffpy-pickem.fly.dev/)
- **Docs:** [docs/deployment/fly.md](docs/deployment/fly.md)

## Further reading

- [docs/testing.md](docs/testing.md) — test suite and manual smoke test
- [docs/db/database.md](docs/db/database.md) — database schema and CLI
- [docs/optimization.md](docs/optimization.md) — optimizer internals
- [docs/streamlit/player-comparison.md](docs/streamlit/player-comparison.md) — Streamlit UI details
- [docs/integration/espn.md](docs/integration/espn.md) — ESPN API integration
- [docs/integration/pickem.md](docs/integration/pickem.md) — Pick'em platform integration
- [docs/deployment/fly.md](docs/deployment/fly.md) — Fly.io deployment guide
- [QUICKSTART.md](QUICKSTART.md) — two-minute walkthrough
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributing guide
- `examples/` — runnable scripts (optimize, pick'em, ESPN league, play analysis)
- `notebooks/` — EDA and solver comparison notebooks

## License

MIT.
