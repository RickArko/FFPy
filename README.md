# FFPy — Fantasy Football Python

A Streamlit app and Python toolkit for fantasy football projections, lineup optimization, play-by-play analytics, and pick'em backtesting. Pulls data from [nflverse](https://nflverse.github.io/), ESPN, or SportsDataIO and runs everything locally against a SQLite database.

## Prerequisites

- A POSIX shell with `make` — Linux, macOS, or **Windows via WSL**
- Internet access for the first-time dependency install

Everything else (`uv`, Python 3.13, the virtualenv, dependencies, DB schema) is installed by `make bootstrap`.

## Quick start

```bash
make bootstrap   # one-time: installs uv, deps, .env, DB schema
make run         # starts Streamlit on http://localhost:8501
make pickem-web PORT=8000   # starts the FastAPI + Vue pick'em tester
make pickem-web-auth-local PORT=8000   # auth-enabled local backend with dev JWTs
```

See [QUICKSTART.md](QUICKSTART.md) for the two-minute walkthrough.

## Make targets

`make help` lists everything. Highlights:

| Target                      | What it does                                     |
|-----------------------------|--------------------------------------------------|
| `make bootstrap`            | First-time setup (idempotent)                    |
| `make install`              | `uv sync` only                                   |
| `make run` / `make dev`     | Launch Streamlit (dev = auto-reload on save)     |
| `make pickem-web`           | Launch the FastAPI + Vue pick'em strategy tester |
| `make pickem-web-auth-local`| Launch the pick'em tester with local auth enabled|
| `make pickem-web-auth-supabase` | Launch the pick'em tester against Supabase auth |
| `make pickem-auth-token`    | Mint a local bearer token for auth testing       |
| `make test` / `make cov`    | Pytest, optionally with coverage                 |
| `make lint` / `make fmt`    | Ruff lint / format                               |
| `make check`                | `lint` + `test` (CI entry point)                 |
| `make db.migrate`           | Create or upgrade the SQLite schema              |
| `make db.load SEASON=Y`     | Load a season of nflverse play-by-play           |
| `make db.update`            | Incrementally append new games                   |
| `make db.stats SEASON=Y`    | Collect ESPN actual stats for that season        |
| `make db.mock SEASON=Y`     | Populate with realistic mock data                |
| `make notebook`             | Jupyter Lab with the analysis dep group          |
| `make clean` / `clean-all`  | Remove caches (+ `.venv`)                        |

Database commands are thin wrappers over the `ffpy-db` CLI:

```bash
uv run ffpy-db --help
uv run ffpy-db load --season 2023 --no-ftn --validate
uv run ffpy-db collect-stats --season 2024 --start-week 1 --end-week 17
```

## Features

- Streamlit app: projections, player comparison, pick'em analyzer
- FastAPI + Vue pick'em strategy tester for historical backtests and strategy comparison
- Lineup optimizer (PuLP) for PPR / Half-PPR / Standard, superflex, custom rosters
- Historical projection model (weighted recent performance)
- ESPN + SportsDataIO integrations with automatic fallback
- Local SQLite with nflverse play-by-play, FTN charting, and snap counts

## Project structure

```
FFPy/
├── Makefile               # All dev/ops commands
├── pyproject.toml         # uv-managed deps, console scripts
├── scripts/
│   └── bootstrap.sh       # First-time setup
├── src/ffpy/
│   ├── app.py             # Streamlit entry       → `ffpy`
│   ├── pickem_web.py      # FastAPI web app       → `ffpy-pickem-web`
│   ├── cli.py             # Database CLI          → `ffpy-db`
│   ├── mock.py            # Mock data generator
│   ├── database.py        # SQLite wrapper
│   ├── nflverse_loader.py # nflverse → DB
│   ├── projections.py     # Historical projection model
│   ├── optimizer.py       # Lineup optimization
│   ├── scoring.py         # Scoring systems
│   ├── integrations/      # ESPN, SportsDataIO
│   ├── migrations/        # SQL schema migrations
│   ├── pages/             # Streamlit pages
│   └── web/               # Static assets for the pick'em tester UI
├── config/                # Scoring + roster presets (JSON)
├── tests/                 # pytest suite
├── notebooks/             # EDA notebooks
├── examples/              # Scripted demos
└── docs/                  # Extended guides
```

## Configuration

Copy the template and edit:

```bash
cp .env.example .env
```

Key settings:

```
API_PROVIDER=espn          # "espn" (free) or "sportsdata" (paid)
NFL_SEASON=2024
DATABASE_PATH=~/.ffpy/ffpy.db
ESPN_LEAGUE_ID=            # Optional: ESPN league integration
```

## Local auth testing

The Vue app now renders a minimal Supabase email/password sign-in shell when a real Supabase project is configured. For the purely local auth target, there is still no browser sign-in because that mode only uses an HS256 dev secret, so the easiest way to test it remains API-first:

```bash
make pickem-web-auth-local PORT=8000
make pickem-auth-token
```

That prints a verified bearer token you can use with `curl`, Postman, or the FastAPI docs. Example:

```bash
TOKEN="$(make -s pickem-auth-token)"
curl -X POST http://127.0.0.1:8000/api/backtests/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": {"name": "AllFavorites", "params": {}},
    "season_start": 2022,
    "season_end": 2022,
    "week_start": 1,
    "week_end": 2,
    "season_type": "REG",
    "require_full_coverage": true,
    "persist": false
  }'
```

To test the rejection path, mint an unverified token:

```bash
make pickem-auth-token TOKEN_ARGS=--unconfirmed
```

When you have a real Supabase project configured in `.env`, run:

```bash
make pickem-web-auth-supabase PORT=8000
```

That enables auth using `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and related settings from `.env`. The Vue frontend will render a minimal Supabase email/password sign-in panel automatically when that public config is present.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Test guidance lives in [TESTING.md](TESTING.md). Deeper documentation (database schema, optimizer internals, Streamlit pages, and the Supabase deployment/auth plan) lives in [`docs/`](docs/), including [docs/security/SUPABASE_HARDENED_IMPLEMENTATION_PLAN.md](docs/security/SUPABASE_HARDENED_IMPLEMENTATION_PLAN.md).

## License

MIT.
