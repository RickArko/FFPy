"""FFPy league data ingestion CLI.

Usage:
    ffpy-ingest espn <league_id> [--season N] [--json|--csv] [--db PATH] [--swid ...] [--s2 ...]
    ffpy-ingest yahoo <league_id> [--season N] [--json|--csv] [--db PATH] [--token ...]
    ffpy-ingest sleeper <league_id> [--season N] [--json|--csv] [--db PATH]
    ffpy-ingest yahoo-auth
    ffpy-ingest yahoo-token --code CODE
    ffpy-ingest leagues-list [--json|--csv] [--db PATH]
    ffpy-ingest leagues-info <id> [--json|--csv] [--db PATH]
    ffpy-ingest roster <league_id> <team_id> [--json|--csv] [--db PATH]
    ffpy-ingest matchups <league_id> <week> [--json|--csv] [--db PATH]
"""

from . import auth, cli, espn, output, sleeper, yahoo

__all__ = ["auth", "cli", "espn", "output", "sleeper", "yahoo"]
