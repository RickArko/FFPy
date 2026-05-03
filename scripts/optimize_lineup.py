#!/usr/bin/env python
"""
Optimize fantasy football lineup from the command line.

Usage:
    # Basic (historical model, skill positions only, week 15)
    uv run python scripts/optimize_lineup.py --week 15

    # Different roster format
    uv run python scripts/optimize_lineup.py --week 15 --roster superflex

    # Lock in specific players
    uv run python scripts/optimize_lineup.py --week 15 \\
        --lock-in "Patrick Mahomes" "Travis Kelce"

    # Compare against your current lineup
    uv run python scripts/optimize_lineup.py --week 15 \\
        --current-lineup "Josh Allen" "Christian McCaffrey" "Bijan Robinson" \\
                         "Tyreek Hill" "Justin Jefferson" "Travis Kelce" "Saquon Barkley"

    # Limit stacking (max 2 players per team)
    uv run python scripts/optimize_lineup.py --week 15 --max-per-team 2

    # Export optimized lineup as JSON
    uv run python scripts/optimize_lineup.py --week 15 --output json > lineup.json

    # Export as CSV
    uv run python scripts/optimize_lineup.py --week 15 --output csv > lineup.csv
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd

from ffpy.data import get_projections
from ffpy.optimizer import (
    LineupOptimizer,
    LineupResult,
    Player,
    PlayerStatus,
    RosterConstraints,
)

ROSTER_PRESETS = {
    "skill-only": RosterConstraints.no_kicker_dst,
    "standard": RosterConstraints.standard,
    "superflex": RosterConstraints.superflex,
}


def projections_to_players(df: pd.DataFrame) -> list:
    """Convert projection DataFrame to Player objects, filtering nulls."""
    df = df[df["projected_points"].notna()].copy()
    df = df.drop_duplicates(subset=["player"], keep="first")

    players = []
    for _, row in df.iterrows():
        players.append(
            Player(
                name=row["player"],
                position=row["position"],
                team=row.get("team", "FA") if pd.notna(row.get("team")) else "FA",
                projected_points=float(row["projected_points"]),
                status=PlayerStatus.AVAILABLE,
                opponent=_safe_str(row.get("opponent")),
                consistency=_safe_float(row.get("consistency")),
            )
        )
    return players


def _safe_float(val):
    if val is None or pd.isna(val):
        return None
    return float(val)


def _safe_str(val):
    if val is None or pd.isna(val):
        return None
    return str(val)


def format_json(result: LineupResult) -> str:
    """Serialize lineup result as JSON."""
    return json.dumps(
        {
            "total_points": round(result.total_points, 2),
            "solve_time_ms": round(result.solve_time_ms, 1),
            "is_optimal": result.is_optimal,
            "improvement_vs_current": (
                round(result.improvement_vs_current, 2) if result.improvement_vs_current is not None else None
            ),
            "starters": [
                {
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "opponent": p.opponent,
                    "projected_points": round(p.projected_points, 2),
                }
                for p in result.starters
            ],
            "bench": [
                {
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "projected_points": round(p.projected_points, 2),
                }
                for p in result.bench
            ],
            "points_by_position": {k: round(v, 2) for k, v in result.points_by_position.items()},
        },
        indent=2,
    )


def format_csv(result: LineupResult) -> str:
    """Serialize lineup result as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["role", "position", "player", "team", "opponent", "projected_points"])
    for p in result.starters:
        writer.writerow(
            ["starter", p.position, p.name, p.team, p.opponent or "", round(p.projected_points, 2)]
        )
    for p in result.bench:
        writer.writerow(["bench", p.position, p.name, p.team, p.opponent or "", round(p.projected_points, 2)])
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="Optimize fantasy football lineup via Integer Linear Programming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--week", type=int, default=1, help="NFL week (1-18). Default: 1")
    parser.add_argument(
        "--data-source",
        choices=["historical", "sample", "api"],
        default="historical",
        help="Projection source. Default: historical",
    )
    parser.add_argument(
        "--roster",
        choices=list(ROSTER_PRESETS.keys()),
        default="skill-only",
        help="Roster format preset. Default: skill-only (QB/RB/WR/TE/FLEX)",
    )
    parser.add_argument(
        "--lock-in",
        nargs="*",
        default=[],
        metavar="NAME",
        help="Player names to force into the starting lineup",
    )
    parser.add_argument(
        "--lock-out",
        nargs="*",
        default=[],
        metavar="NAME",
        help="Player names to force to the bench",
    )
    parser.add_argument(
        "--max-per-team",
        type=int,
        default=0,
        help="Max players from same team (0 = no limit). Default: 0",
    )
    parser.add_argument(
        "--current-lineup",
        nargs="*",
        default=[],
        metavar="NAME",
        help="Your current starters (enables improvement calculation)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format. Default: text",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show PuLP solver output",
    )

    args = parser.parse_args()

    print(f"Loading Week {args.week} projections ({args.data_source})...", file=sys.stderr)
    projections = get_projections(
        week=args.week,
        use_real_data=(args.data_source == "api"),
        use_historical_model=(args.data_source == "historical"),
    )

    if projections.empty:
        print(f"ERROR: No projection data for week {args.week}", file=sys.stderr)
        sys.exit(1)

    players = projections_to_players(projections)
    print(f"Loaded {len(players)} players", file=sys.stderr)

    constraints = ROSTER_PRESETS[args.roster]()

    overlap = set(args.lock_in) & set(args.lock_out)
    if overlap:
        print(
            f"ERROR: players cannot be both locked-in and locked-out: {', '.join(overlap)}", file=sys.stderr
        )
        sys.exit(1)

    constraints.locked_in = set(args.lock_in)
    constraints.locked_out = set(args.lock_out)
    if args.max_per_team > 0:
        constraints.max_players_per_team = args.max_per_team

    available_positions = {p.position for p in players}
    required = set(constraints.positions.keys())
    missing = required - available_positions
    if missing:
        print(
            f"ERROR: required positions missing from projections: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        print("Hint: try --roster skill-only if projections lack K/DST", file=sys.stderr)
        sys.exit(1)

    current_lineup = None
    if args.current_lineup:
        current_names = set(args.current_lineup)
        current_lineup = [p for p in players if p.name in current_names]
        if len(current_lineup) != len(current_names):
            missing_names = current_names - {p.name for p in current_lineup}
            print(
                f"WARNING: current-lineup names not found in projections: {', '.join(sorted(missing_names))}",
                file=sys.stderr,
            )

    try:
        optimizer = LineupOptimizer(constraints)
        result = optimizer.optimize(players, current_lineup=current_lineup, verbose=args.verbose)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Install PuLP with: uv add pulp", file=sys.stderr)
        sys.exit(1)

    if args.output == "json":
        print(format_json(result))
    elif args.output == "csv":
        print(format_csv(result))
    else:
        print(optimizer.analyze_lineup(result))


if __name__ == "__main__":
    main()
