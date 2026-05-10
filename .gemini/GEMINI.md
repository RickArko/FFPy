# GEMINI.md — FFPy

Guidance for the Gemini CLI when working in this repo. Mirrors the rules
in `CLAUDE.md` so behavior is consistent across providers.

## Project Overview

FFPy is a Streamlit app + Python toolkit for fantasy football: weekly
projections, lineup optimization (PuLP/CBC ILP), pick'em backtesting,
ESPN league integration, and nflverse play-by-play ingestion. Data lives
in a local SQLite database; a FastAPI + Vue surface (`ffpy-pickem-web`)
exposes the pick'em strategy tester.

## Key Commands

```bash
make bootstrap      # one-time setup
make run            # Streamlit on :8501
make pickem-web PORT=8000
make test           # pytest
make check          # ruff + pytest (CI entry)
make db.load SEASON=2024
uv run ffpy-db --help
```

## Architecture

Source under `src/ffpy/`. Entry points: `ffpy` (Streamlit app),
`ffpy-pickem-web` (FastAPI), `ffpy-db` (SQLite CLI), declared in
`pyproject.toml [project.scripts]`. SQLite schema versioned via
`src/ffpy/migrations/`. The canonical module map is `AI-CONTEXT.md` at
the repo root — read it first when orienting.

## Default Working Mode

- Prefer implementation over speculation.
- Decompose substantial work into atomic tasks.
- Call out blockers and assumptions explicitly.
- Run `make check` (ruff + pytest) before declaring work done.

## Conventions

- Python 3.13+, `uv` build/package manager. Invoke Python via `uv run …`.
- Format/lint with `ruff` (line-length=110). `make fmt` before commits.
- Tests in `tests/`. Add tests for new scoring rules, optimizer
  constraints, or data parsers.
- DB changes go in new migration files; never edit merged migrations.
- `.env` files: no trailing inline comments — they become part of the value.
- Do not autonomously add deps via `uv add` or modify `pyproject.toml` —
  confirm with the user first. For experiments, use notebook-local installs.

## Output Preferences

- Concise summaries first, then details.
- Include exact file paths and commands.
- Show verification status and any gaps.

## AI-enrichment

This repo is enriched with `ai-enrich`. The Gemini CLI loads context
from `.gemini/settings.json` → `contextFiles`, which by default includes
`GEMINI.md` and `.claude/wiki/AGENTS.md`. The wiki schema and conventions
apply equally to Gemini-driven work.
