#!/usr/bin/env bash
# FFPy bootstrap — first-time setup.
# Installs uv if missing, syncs Python deps, seeds .env, runs DB migration.
# Idempotent; safe to re-run.

set -euo pipefail

cd "$(dirname "$0")/.."

info() { printf "\033[1;34m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m==>\033[0m %s\n" "$*" >&2; }
err()  { printf "\033[1;31m==>\033[0m %s\n" "$*" >&2; }

if ! command -v uv >/dev/null 2>&1; then
    info "uv not found; installing via astral.sh installer"
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # The installer drops uv into ~/.local/bin and emits an env file.
    if [ -f "$HOME/.local/bin/env" ]; then
        # shellcheck disable=SC1091
        . "$HOME/.local/bin/env"
    else
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv >/dev/null 2>&1; then
        err "uv installed but not on PATH. Open a new shell and re-run: make bootstrap"
        exit 1
    fi
fi

info "uv: $(uv --version)"

info "Syncing Python dependencies (uv sync)"
uv sync

info "Registering Jupyter kernel 'ffpy'"
uv run python -m ipykernel install --user --name ffpy --display-name "Python (FFPy)"

if [ ! -f .env ]; then
    info "Seeding .env from .env.example (edit to add API keys)"
    cp .env.example .env
else
    info ".env already present; leaving it alone"
fi

info "Running database migration"
uv run ffpy-db migrate

echo
info "Bootstrap complete."
echo "  Start the app:           make run"
echo "  Load a season of data:   make db.load SEASON=2024"
echo "  See all make targets:    make help"
