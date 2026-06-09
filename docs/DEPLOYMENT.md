### What was added:

- Dockerfile for a production container
- fly.toml with a mounted SQLite volume at /data
- docker/entrypoint.sh to drop from root to a non-root app user
- .github/workflows/ci-cd.yml for CI on PRs/pushes and deploys on main
- docs/deployment/fly.md with the exact deployment steps
- README.md with a short deployment section
- ffpy.pickem_web now binds from HOST and PORT env vars instead of
hardcoding localhost in the container

### Secure workflow:

- SQLite lives on a Fly volume, not inside the image
- WEB_AUTH_ENABLED=true by default on Fly so auth fails closed if
secrets are missing

- Supabase and hash-salt values stay in Fly secrets, not GitHub or the image

- GitHub Actions runs tests and a Docker build first, then deploys only from main

- The container runs as a non-root app user after startup initialization

### The deploy flow is:

```bash
fly launch --no-deploy
fly volumes create ffpy_data --region iad --size 1
fly secrets set \
WEB_AUTH_ENABLED=true \
DATABASE_PATH=/data/ffpy.db \
SUPABASE_URL=https://<your-project>.supabase.co \
SUPABASE_ANON_KEY=<anon-key> \
SUPABASE_JWT_SECRET=<jwt-secret> \
SUPABASE_JWT_AUDIENCE=authenticated \
SUPABASE_FETCH_USER_ON_VERIFY=true \
ABUSE_HASH_SALT=<random-long-string>
fly deploy
```

### GitHub, add:

- `FLY_API_TOKEN` as a secret
- optionally a protected production environment for the deploy job

I verified the app still passes uv run pytest tests/test_pickem_api.py after the changes.

If you want, I can also add a second Fly app for the Streamlit projections UI, but this setup is for the `FastAPI/Vue` pick'em service you were running in the logs.



### Optimization Notebooks

Notebook	Topics	Cells	What you'll learn
01_scoring_systems_impact.ipynb	Scoring & valuation	21 (8 code)	How PPR/Half/Standard/custom scoring changes player value & optimal lineups
02_optimizer_constraints.ipynb	Constraint deep dive	23 (9 code)	Superflex, locks, injuries, team stacks, salary cap, combined constraints
03_projection_uncertainty.ipynb	Robust lineups	24 (9 code)	Monte Carlo simulation, core starters, ceiling vs floor, sensitivity analysis

All three are self-contained — no database needed, they construct player pools in-memory. Each builds on the last, so the recommended order is 1 → 2 → 3 → (the existing xpress_vs_pulp for solver internals).

**Quick links:**
- `scripts/generate_optimization_notebooks.py` — single-source generator (edit this to add sections)
- Regenerate with: `uv run python scripts/generate_optimization_notebooks.py`
- Launch with: `make notebook → notebooks/01_scoring_systems_impact.ipynb`


## Projections App `VUE.js`

Implemented an enhanced Vue projections app alongside the existing pick’em tester.

### What changed:

- Added /projections static Vue page.
- Added /api/projections with source, week,
position, and top_n query controls.

- Supports historical model, API data, and sample
data with sample fallback.

- Added sortable/searchable player board, position
filters, metric cards, position summaries, and
leaderboards.

- Added tests for the projections page and filtered
sample API output.

### Key files:

- src/ffpy/pickem_web.py
- src/ffpy/web/pickem_tester/projections.html
- src/ffpy/web/pickem_tester/projections.js
- src/ffpy/web/pickem_tester/styles.css
- tests/test_pickem_api.py

### Verified:

- `uv run pytest tests/test_pickem_api.py` -> **15 passed**

- `uv run ruff check src/ffpy/pickem_web.py tests/test_pickem_api.py` -> **passed**

Run the existing web app and open
http://127.0.0.1:8501/projections.

