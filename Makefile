# FFPy — Fantasy Football Python
# Canonical cross-platform entry point. Windows users: run from WSL.
# See `make help` for all targets.

.DEFAULT_GOAL := help
.PHONY: help bootstrap install run dev pickem-web notebook test cov lint fmt check \
        db.migrate db.load db.update db.stats db.mock clean clean-all

# Override on the CLI, e.g. `make db.load SEASON=2023`
SEASON     ?= 2024
START_WEEK ?= 1
END_WEEK   ?= 17
PORT       ?= 8501
UV         ?= uv

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "; \
	             printf "\nFFPy — make targets\n\nUsage: make <target> [VAR=value]\n\n"} \
	     /^[a-zA-Z_.-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\nVariables (override on CLI): SEASON=%s PORT=%s START_WEEK=%s END_WEEK=%s\n\n" \
	        "$(SEASON)" "$(PORT)" "$(START_WEEK)" "$(END_WEEK)"

# ---- Setup --------------------------------------------------------

bootstrap: ## First-time setup (installs uv, syncs deps, seeds .env, migrates DB)
	@bash scripts/bootstrap.sh

install: ## Sync dependencies and register the `ffpy` Jupyter kernel
	$(UV) sync
	@echo "==> Registering Jupyter kernel 'ffpy'"
	@$(UV) run python -m ipykernel install --user --name ffpy --display-name "Python (FFPy)"

# ---- App ----------------------------------------------------------

run: ## Start the Streamlit app (PORT=8501)
	$(UV) run streamlit run src/ffpy/app.py --server.port $(PORT)

dev: ## Start the app with auto-reload
	$(UV) run streamlit run src/ffpy/app.py --server.port $(PORT) --server.runOnSave=true

pickem-web: ## Start the FastAPI + Vue pick'em tester (PORT=8000 recommended)
	.venv/bin/python -m ffpy.pickem_web --port $(PORT)

notebook: ## Launch Jupyter Lab (analysis dep group)
	$(UV) run --group analysis jupyter lab

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

check: lint test ## Lint + test (CI entry point)

# ---- Database -----------------------------------------------------

db.migrate: ## Create or upgrade the SQLite schema
	$(UV) run ffpy-db migrate

db.load: ## Load play-by-play for a season (SEASON=2024)
	$(UV) run ffpy-db load --season $(SEASON)

db.update: ## Incrementally update the current season
	$(UV) run ffpy-db update

db.stats: ## Collect actual stats from ESPN (SEASON, START_WEEK, END_WEEK)
	$(UV) run ffpy-db collect-stats --season $(SEASON) --start-week $(START_WEEK) --end-week $(END_WEEK)

db.mock: ## Populate with realistic mock data (SEASON=2024)
	$(UV) run ffpy-db mock --season $(SEASON)

# ---- Cleanup ------------------------------------------------------

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Also remove the virtualenv
	rm -rf .venv
