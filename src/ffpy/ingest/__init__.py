"""FFPy league data ingestion CLI.

Usage:
    ffpy-ingest espn <league_id> [--season N] [--json|--csv|--db]
    ffpy-ingest yahoo <league_id> [--season N] [--json|--csv|--db]
    ffpy-ingest sleeper <league_id> [--season N] [--json|--csv|--db]
    ffpy-ingest yahoo auth
    ffpy-ingest yahoo token --code CODE
    ffpy-ingest leagues list [--db PATH]
    ffpy-ingest leagues info <id> [--db PATH]
    ffpy-ingest roster <league_id> <team_id> [--db PATH] [--json|--csv]
    ffpy-ingest matchups <league_id> <week> [--db PATH] [--json|--csv]
"""

from . import auth, cli, espn, output, sleeper, yahoo

__all__ = ["auth", "cli", "espn", "output", "sleeper", "yahoo"]
