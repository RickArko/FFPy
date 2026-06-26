# Testing Guide

Verify the app is working end-to-end and learn where to plug in new tests.

## Automated test suite

```bash
make test          # pytest
make cov           # pytest + coverage (terminal + htmlcov/)
make check         # lint + test (CI entry point)
```

Tests live in `tests/`. Coverage targets `src/ffpy` (see `[tool.coverage.run]` in `pyproject.toml`). Add new test files as `tests/test_*.py`.

## Manual smoke test (30 seconds)

### 1. Run the app

```bash
make run
```

> First time? `make bootstrap` before this.

### 2. Verify in browser

The app opens at `http://localhost:8501`. Expect:

- **Title:** "FFPy - Fantasy Football Analytics"
- **Sidebar:** Data source radio, week / position / count filters
- **Main:** Projection table + metrics

### 3. Exercise the filters

- **Data source:** toggle Historical Model / API Data / Sample Data — the badge under the radio updates (`📊 database-driven`, `API: ESPN`, or `🎲 sample`)
- **Week:** change 1–18; data refreshes
- **Position:** QB / RB / WR / TE / All Positions
- **Count:** slider 5–50; table resizes

## API provider matrix

Set in `.env`, then re-run `make run`.

### ESPN (default, free)

```
API_PROVIDER=espn
```

Expect real NFL players, current season, `API: ESPN` in the sidebar.

### SportsDataIO (paid)

```
API_PROVIDER=sportsdata
SPORTSDATA_API_KEY=<your key>
```

Expect `API: SPORTSDATA` and richer projections. Free tier is 1000 calls/month.

### Fallback

Setting `API_PROVIDER=invalid` (or any unrecognized value) falls back to sample data with a warning banner.

## Verifying configuration

```bash
uv run python -c "from ffpy.config import Config; print(Config.debug_config())"
```

## Database commands

All DB workflows run through the `ffpy-db` CLI. Each has a Makefile shortcut.

```bash
make db.migrate                       # schema setup
make db.load SEASON=2024              # nflverse play-by-play for a season
make db.update                        # add new games to the current season
make db.stats SEASON=2024             # ESPN actual stats
make db.mock SEASON=2024              # realistic mock data for offline dev

# Raw CLI (for flags not exposed as make vars):
uv run ffpy-db load --start-season 2020 --end-season 2024 --validate
uv run ffpy-db collect-stats --season 2024 --start-week 1 --end-week 17
```

Check the DB is populated:

```bash
uv run python -c "from ffpy.database import FFPyDatabase; db=FFPyDatabase(); s=db.get_actual_stats(season=2024); print(f'records={len(s)} weeks={s.week.nunique()} players={s.player.nunique()}')"
```

## Common issues

| Symptom                            | Fix                                                         |
|------------------------------------|-------------------------------------------------------------|
| `ModuleNotFoundError: ffpy`        | `make install`                                              |
| Port 8501 already in use           | `make run PORT=8502`                                        |
| "No historical data found"         | `make db.mock SEASON=2024` or `make db.stats SEASON=2024`   |
| SportsDataIO returns 401           | Verify `SPORTSDATA_API_KEY` in `.env`, or drop back to ESPN |
| `uv: command not found`            | Re-run `make bootstrap` in a fresh shell                    |

## Testing integrations directly

```bash
# ESPN
uv run python -c "from ffpy.integrations import ESPNIntegration; df = ESPNIntegration().get_projections(week=1, season=2025); print(len(df), df.head())"

# Cache behavior
uv run python -c "
from ffpy.data import get_projections
import time
for i in range(2):
    t = time.time()
    df = get_projections(week=1, use_real_data=True)
    print(f'call {i}: {time.time()-t:.2f}s, {len(df)} rows')
"
```

## Success criteria

- `make check` exits green
- `make run` reaches the Streamlit page with real or mock data rendered
- Data source toggle changes the table contents
- Week / position / count filters update the table without errors
- At least one of the API providers returns data (or the fallback banner shows)
