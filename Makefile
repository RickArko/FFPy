# FFPy — Fantasy Football Python
# Canonical cross-platform entry point. Windows users: run from WSL.
# See `make help` for all targets.

.DEFAULT_GOAL := help
.PHONY: help bootstrap install data full-data run dev pickem-web pickem-web-auth-local \
        pickem-web-auth-supabase pickem-auth-token notebook test cov lint fmt check \
        precommit precommit-install precommit-update \
        db.prepare db.migrate db.load db.update db.stats db.mock \
        db.compute-stats db.ngs db.injuries db.audit db.dfs db.adp db.depth-chart db.weather \
        supabase.check fly.app fly.volume fly.secrets fly.secrets-list \
        fly.deploy fly.status fly.logs fly.token clean clean-all

# Override on the CLI, e.g. `make db.load SEASON=2023`
SEASON     ?= 2024
START_WEEK ?= 1
END_WEEK   ?= 17
PORT       ?= 8501
UV         ?= uv
DATA_MODE  ?= real
STATS_SOURCE ?= nflverse
FLY_APP    ?= ffpy-pickem
FLY_REGION ?= iad
FLY_VOLUME_SIZE ?= 1
FLY        ?= $(or $(shell command -v fly 2>/dev/null),$(shell command -v flyctl 2>/dev/null),$(wildcard $(HOME)/.fly/bin/fly),fly)
PICKEM_DB_PATH ?= $(HOME)/.ffpy/ffpy.db
PREPARE_ARGS ?=
AUTH_JWT_SECRET ?= local-supabase-jwt-secret-change-me-123456
AUTH_EMAIL      ?= demo@example.com
TOKEN_ARGS      ?= --confirmed
DATA_MODE_ARGS = $(if $(filter mock,$(DATA_MODE)),--mock,)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "; \
	             printf "\nFFPy — make targets\n\nUsage: make <target> [VAR=value]\n\n"} \
	     /^[a-zA-Z_.-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\nVariables (override on CLI): SEASON=%s PORT=%s START_WEEK=%s END_WEEK=%s DATA_MODE=%s STATS_SOURCE=%s\n\n" \
	        "$(SEASON)" "$(PORT)" "$(START_WEEK)" "$(END_WEEK)" "$(DATA_MODE)" "$(STATS_SOURCE)"

# ---- Setup --------------------------------------------------------

bootstrap: ## First-time setup (installs uv, syncs deps, seeds .env, migrates DB)
	@bash scripts/bootstrap.sh

install: ## Sync dependencies, register Jupyter kernel, and install git hooks
	$(UV) sync
	@echo "==> Registering Jupyter kernel 'ffpy'"
	@$(UV) run python -m ipykernel install --user --name ffpy --display-name "Python (FFPy)"
	@if git rev-parse --git-dir >/dev/null 2>&1; then \
		echo "==> Installing pre-commit hooks (runs CI lint on every commit)"; \
		$(UV) run pre-commit install; \
	else \
		echo "==> Skipping pre-commit (not a git checkout)"; \
	fi

data: db.prepare ## Generate all required app data (DATA_MODE=real|mock)

full-data: db.prepare db.compute-stats db.ngs db.injuries  ## Full pipeline: PBP → stats → advanced stats → NGS → injuries → depth charts → weather → audit
	$(UV) run ffpy-db load-depth-charts --season $(SEASON)
	$(UV) run ffpy-db add-weather --season $(SEASON)
	-$(UV) run ffpy-db audit --exit-zero
	@echo ""
	@echo "Full data pipeline complete. Run \`make run\` to launch the app."

# ---- App ----------------------------------------------------------

run: ## Start the Streamlit app (PORT=8501)
	$(UV) run streamlit run src/ffpy/app.py --server.port $(PORT)

dev: ## Start the app with auto-reload
	$(UV) run streamlit run src/ffpy/app.py --server.port $(PORT) --server.runOnSave=true

pickem-web: ## Start the FastAPI + Vue pick'em tester (PORT=8000 recommended, PICKEM_DB_PATH)
	DATABASE_PATH="$(PICKEM_DB_PATH)" .venv/bin/python -m ffpy.pickem_web --port $(PORT)

pickem-web-auth-local: ## Start the pick'em tester with local auth enabled (HS256 dev tokens)
	DATABASE_PATH="$(PICKEM_DB_PATH)" WEB_AUTH_ENABLED=true SUPABASE_JWT_SECRET="$(AUTH_JWT_SECRET)" SUPABASE_FETCH_USER_ON_VERIFY=false .venv/bin/python -m ffpy.pickem_web --port $(PORT)

pickem-web-auth-supabase: ## Start the pick'em tester with auth enabled using Supabase settings from .env
	DATABASE_PATH="$(PICKEM_DB_PATH)" WEB_AUTH_ENABLED=true .venv/bin/python -m ffpy.pickem_web --port $(PORT)

pickem-auth-token: ## Mint a local bearer token for pickem-web-auth-local
	.venv/bin/python -m ffpy.dev_auth_token --secret "$(AUTH_JWT_SECRET)" --email "$(AUTH_EMAIL)" $(TOKEN_ARGS)

notebook: ## Launch Jupyter Lab (analysis dep group)
	$(UV) run --group analysis jupyter lab

supabase.check: ## Validate local Supabase URL/key from .env before setting Fly secrets
	$(UV) run python scripts/check_supabase.py

# ---- Quality ------------------------------------------------------

test: ## Run the test suite
	$(UV) run pytest

cov: ## Run tests with coverage (terminal + HTML in htmlcov/)
	$(UV) run coverage run -m pytest
	$(UV) run coverage report
	$(UV) run coverage html

lint: ## Lint with ruff
	$(UV) run ruff check .

fmt: ## Format with ruff
	$(UV) run ruff format .

precommit: ## Run pre-commit hooks on all files (install via `make precommit-install`)
	$(UV) run pre-commit run --all-files

precommit-install: ## Install pre-commit hooks into .git/hooks/ (also run by `make install`)
	$(UV) run pre-commit install

precommit-update: ## Update pre-commit hook versions to latest
	$(UV) run pre-commit autoupdate

check: lint test ## Lint + test (CI entry point)

# ---- Database -----------------------------------------------------

db.prepare: ## Generate all required app data (SEASON, START_WEEK, END_WEEK, DATA_MODE)
	$(UV) run ffpy-db prepare --season $(SEASON) --start-week $(START_WEEK) --end-week $(END_WEEK) --stats-source $(STATS_SOURCE) $(DATA_MODE_ARGS) $(PREPARE_ARGS)

db.migrate: ## Create or upgrade the SQLite schema
	$(UV) run ffpy-db migrate

db.load: ## Load play-by-play for a season (SEASON=2024)
	$(UV) run ffpy-db load --season $(SEASON)

db.update: ## Incrementally update the current season
	$(UV) run ffpy-db update

db.stats: ## Collect actual stats (STATS_SOURCE=nflverse|espn)
	$(UV) run ffpy-db collect-stats --season $(SEASON) --start-week $(START_WEEK) --end-week $(END_WEEK) --source $(STATS_SOURCE)

db.mock: ## Populate with realistic mock data (SEASON=2024)
	$(UV) run ffpy-db mock --season $(SEASON)

db.compute-stats: ## Compute derived advanced player stats (SEASON=2024)
	$(UV) run ffpy-db compute-stats --season $(SEASON)

db.ngs: ## Load Next Gen Stats for a season (SEASON=2024)
	$(UV) run ffpy-db load-ngs --season $(SEASON)

db.injuries: ## Load injury data for a season (SEASON=2024)
	$(UV) run ffpy-db load-injuries --season $(SEASON)

db.audit: ## Run data quality audit
	$(UV) run ffpy-db audit

db.dfs: ## Load DFS salaries (placeholder, SEASON=2024)
	$(UV) run ffpy-db load-dfs --season $(SEASON)

db.adp: ## Load ADP data (placeholder, SEASON=2024)
	$(UV) run ffpy-db load-adp --season $(SEASON)

db.depth-chart: ## Load depth charts (SEASON=2024)
	$(UV) run ffpy-db load-depth-charts --season $(SEASON)

db.weather: ## Add historical weather data (SEASON=2024)
	$(UV) run ffpy-db add-weather --season $(SEASON)

# ---- Fly.io -------------------------------------------------------

fly.app: ## Create the Fly app if needed (FLY_APP=ffpy-pickem)
	$(FLY) apps create $(FLY_APP)

fly.volume: ## Create the persistent SQLite volume (FLY_APP, FLY_REGION, FLY_VOLUME_SIZE)
	$(FLY) volumes create ffpy_data --app $(FLY_APP) --region $(FLY_REGION) --size $(FLY_VOLUME_SIZE)

fly.secrets: ## Set Fly runtime secrets from .env or shell exports (FLY_APP=ffpy-pickem)
	FLY_APP="$(FLY_APP)" FLY_BIN="$(FLY)" bash scripts/fly_set_secrets.sh

fly.secrets-list: ## List Fly secret names without values (FLY_APP=ffpy-pickem)
	$(FLY) secrets list --app $(FLY_APP)

fly.deploy: ## Deploy to Fly.io using fly.toml (FLY_APP=ffpy-pickem)
	$(FLY) deploy --app $(FLY_APP)

fly.status: ## Show Fly app status (FLY_APP=ffpy-pickem)
	$(FLY) status --app $(FLY_APP)

fly.logs: ## Tail Fly app logs (FLY_APP=ffpy-pickem)
	$(FLY) logs --app $(FLY_APP)

fly.token: ## Create a GitHub Actions deploy token for this Fly app
	$(FLY) tokens create deploy -a $(FLY_APP)

# ---- Cleanup ------------------------------------------------------

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Also remove the virtualenv
	rm -rf .venv
