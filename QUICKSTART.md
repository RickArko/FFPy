# Quick Start

Two commands get you running. Works on Linux, macOS, and Windows (via WSL).

## First-time setup

```bash
make bootstrap
```

This installs `uv`, syncs Python dependencies, seeds `.env` from the template, and creates the SQLite database. Safe to re-run any time.

## Run the app

```bash
make run
```

The Streamlit app opens at `http://localhost:8501`. Stop with `Ctrl+C`.

## Common next steps

| You want to…                        | Run                                   |
|-------------------------------------|---------------------------------------|
| Load a real NFL season              | `make db.load SEASON=2024`            |
| Top up the current season weekly    | `make db.update`                      |
| Populate a realistic mock season    | `make db.mock SEASON=2024`            |
| Pull actual stats from ESPN         | `make db.stats SEASON=2024`           |
| Dev mode (auto-reload on save)      | `make dev`                            |
| Run the test suite                  | `make test`                           |
| Launch Jupyter for EDA              | `make notebook`                       |
| See every target with a description | `make help`                           |

All database targets are thin wrappers over the `ffpy-db` CLI — run `uv run ffpy-db --help` for the full surface.

## Windows note

Run all commands from **WSL** (Ubuntu recommended). `make` and `bash` need to be in your shell. The native `cmd.exe` / PowerShell path is intentionally unsupported so there's exactly one blessed flow to maintain.

## Troubleshooting

- **`command not found: uv` right after bootstrap** — open a new shell, or `source ~/.local/bin/env`, then re-run `make bootstrap`.
- **Port 8501 already in use** — `make run PORT=8502`.
- **Browser doesn't open** — navigate to `http://localhost:8501` manually.
- **Need API keys** — edit `.env` (see `.env.example` for the list).
