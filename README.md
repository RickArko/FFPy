# FFPy - Fantasy Football Python

A Streamlit app and Python toolkit for fantasy football projections, lineup optimization, play-by-play analytics, and pick'em backtesting. Pulls data from [nflverse](https://nflverse.github.io/), ESPN, or SportsDataIO and runs everything locally against a SQLite database.

![Project Logo](docs/assets/static/FFPy.png)

---

## Quick start

```bash
make bootstrap   # one-time: installs uv, deps, .env, DB schema
make data        # loads app data for the default season (or `DATA_MODE=mock` for offline)
make run         # starts Streamlit on http://localhost:8501
```

See [QUICKSTART.md](QUICKSTART.md) for the two-minute walkthrough.

## Make targets

`make help` lists everything. Key targets:

| Target                      | What it does                                     |
|-----------------------------|--------------------------------------------------|
| `make bootstrap`            | First-time setup (idempotent)                    |
| `make data`                 | Generate required app data for the default season |
| `make run` / `make dev`     | Launch Streamlit (dev = auto-reload on save)     |
| `make pickem-web PORT=8000` | Launch the FastAPI + Vue pick'em strategy tester |
| `make test` / `make cov`    | Pytest, optionally with coverage                 |
| `make lint` / `make fmt`    | Ruff lint / format                               |
| `make check`                | `lint` + `test` (CI entry point)                 |
| `make db.load SEASON=Y`     | Load nflverse play-by-play for a season          |
| `make notebook`             | Jupyter Lab with analysis deps                   |

Database targets wrap the `ffpy-db` CLI — `uv run ffpy-db --help` for the full surface.

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

## Deployment

Production Dockerfile + `fly.toml` in repo. CI builds and deploys to Fly.io on `main` push. See [docs/deployment/fly.md](docs/deployment/fly.md).

## Further reading

- [TESTING.md](TESTING.md) — test suite and manual smoke test
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributing guide
- [QUICKSTART.md](QUICKSTART.md) — two-minute walkthrough
- `docs/` — database guide, optimizer internals, Streamlit UI details, ESPN integration, auth plan
- `examples/` — runnable scripts (optimize, pick'em, ESPN league, play analysis)
- `notebooks/` — EDA and solver comparison notebooks

## License

MIT.
