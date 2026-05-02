"""
Lineup Optimizer - Generate optimal fantasy football lineups.

Uses Integer Linear Programming (PuLP/CBC) to compute the optimal starting
lineup given projections, roster constraints, and optional player locks.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from ffpy.data import get_projections
from ffpy.optimizer import (
    LineupOptimizer,
    LineupResult,
    Player,
    PlayerStatus,
    RosterConstraints,
)


ROSTER_PRESETS = {
    "Skill Positions Only (QB/RB/WR/TE/FLEX)": RosterConstraints.no_kicker_dst,
    "Standard (QB/RB/WR/TE/FLEX/K/DST)": RosterConstraints.standard,
    "Superflex": RosterConstraints.superflex,
}


def main():
    """Main entry point for lineup optimizer page."""
    st.set_page_config(
        page_title="Lineup Optimizer - FFPy",
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ Lineup Optimizer")
    st.markdown(
        "Find your optimal starting lineup using Integer Linear Programming. "
        "Maximizes projected points subject to roster constraints and optional player locks."
    )
    st.markdown("---")

    # === SIDEBAR ===
    with st.sidebar:
        st.header("Optimization Settings")

        week = st.selectbox(
            "Week",
            options=list(range(1, 19)),
            index=14,
            help="NFL week for projections",
        )

        data_source = st.radio(
            "Data Source",
            options=["Historical Model", "Sample Data", "API Data"],
            index=0,
            help=(
                "Historical Model: database-driven projections (recommended)\n\n"
                "Sample Data: hardcoded demo players\n\n"
                "API Data: ESPN/SportsDataIO projections"
            ),
        )

        roster_preset = st.selectbox(
            "Roster Format",
            options=list(ROSTER_PRESETS.keys()),
            index=0,
            help="Lineup structure and position requirements",
        )

        st.markdown("---")
        st.subheader("Advanced")

        max_per_team = st.number_input(
            "Max Players Per Team",
            min_value=0,
            max_value=10,
            value=0,
            help="0 = no limit. Use to avoid over-stacking one team.",
        )

    # === LOAD PROJECTIONS ===
    use_historical = data_source == "Historical Model"
    use_real = data_source == "API Data"

    with st.spinner(f"Loading Week {week} projections..."):
        projections = get_projections(
            week=week,
            use_real_data=use_real,
            use_historical_model=use_historical,
        )

    if projections.empty:
        st.error("No projection data available. Try a different data source or week.")
        return

    # Clean projections
    projections = projections[projections["projected_points"].notna()].copy()
    projections = projections.drop_duplicates(subset=["player"], keep="first")

    if projections.empty:
        st.error("All projections have null points. Try a different data source.")
        return

    st.caption(f"📊 Loaded {len(projections)} players for Week {week}")

    # === PLAYER LOCKS ===
    st.subheader("🔒 Player Locks (Optional)")
    st.caption("Force specific players to start or sit.")

    all_players = sorted(projections["player"].unique().tolist())

    col_lock_a, col_lock_b = st.columns(2)
    with col_lock_a:
        locked_in = st.multiselect(
            "Must Start",
            options=all_players,
            help="Forces these players into the lineup",
        )
    with col_lock_b:
        locked_out = st.multiselect(
            "Must Bench",
            options=all_players,
            help="Forces these players to the bench",
        )

    overlap = set(locked_in) & set(locked_out)
    if overlap:
        st.error(f"Players cannot be both locked-in and locked-out: {', '.join(overlap)}")
        return

    # === CURRENT LINEUP (optional) ===
    with st.expander("📋 Current Lineup (optional — compute improvement vs optimal)"):
        current_lineup_names = st.multiselect(
            "Select your current starters",
            options=all_players,
            help="If set, shows point delta between your lineup and the optimal",
        )

    # === BUILD CONSTRAINTS ===
    constraints = ROSTER_PRESETS[roster_preset]()
    constraints.locked_in = set(locked_in)
    constraints.locked_out = set(locked_out)
    if max_per_team > 0:
        constraints.max_players_per_team = max_per_team

    # Validate position coverage
    available_positions = set(projections["position"].unique())
    required = set(constraints.positions.keys())
    missing = required - available_positions
    if missing:
        st.warning(
            f"⚠️ Required positions missing from projections: **{', '.join(sorted(missing))}**. "
            "Switch to 'Skill Positions Only' roster format, or pick a different data source."
        )
        return

    # === CONVERT TO PLAYER OBJECTS ===
    players = _projections_to_players(projections)

    current_lineup = None
    if current_lineup_names:
        name_set = set(current_lineup_names)
        current_lineup = [p for p in players if p.name in name_set]

    # === OPTIMIZE ===
    st.markdown("---")
    st.subheader("🏆 Optimal Lineup")

    try:
        optimizer = LineupOptimizer(constraints)
        with st.spinner("Solving optimization..."):
            result = optimizer.optimize(players, current_lineup=current_lineup)
    except ValueError as e:
        st.error(f"❌ Cannot optimize: {e}")
        st.info(
            "Common causes: insufficient players for a required position, "
            "conflicting locks, or an infeasible team-stack limit."
        )
        return
    except ImportError as e:
        st.error(f"❌ Optimization library not available: {e}")
        st.code("uv add pulp", language="bash")
        return

    # === METRICS ===
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Projected Points", f"{result.total_points:.1f}")
    with col2:
        st.metric("Starters", len(result.starters))
    with col3:
        st.metric("Solve Time", f"{result.solve_time_ms:.0f} ms")
    with col4:
        if result.improvement_vs_current is not None:
            st.metric(
                "vs Current Lineup",
                f"{result.improvement_vs_current:+.1f} pts",
                delta=f"{result.improvement_vs_current:+.1f}",
            )

    # === RESULTS TABS ===
    tab1, tab2, tab3, tab4 = st.tabs(["🟢 Starting Lineup", "💺 Bench", "📊 Breakdown", "📋 Text Report"])

    with tab1:
        _show_starters(result)

    with tab2:
        _show_bench(result)

    with tab3:
        _show_breakdown(result, current_lineup)

    with tab4:
        st.code(optimizer.analyze_lineup(result), language="text")


def _projections_to_players(df: pd.DataFrame) -> list:
    """Convert projection DataFrame rows to Player objects."""
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
                passing_yards=_safe_float(row.get("passing_yards")),
                passing_tds=_safe_float(row.get("passing_tds")),
                rushing_yards=_safe_float(row.get("rushing_yards")),
                rushing_tds=_safe_float(row.get("rushing_tds")),
                receiving_yards=_safe_float(row.get("receiving_yards")),
                receiving_tds=_safe_float(row.get("receiving_tds")),
                receptions=_safe_float(row.get("receptions")),
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


def _show_starters(result: LineupResult):
    """Display starting lineup with position chart."""
    starters_by_pos = result.get_starters_by_position()

    rows = []
    for pos in sorted(starters_by_pos.keys()):
        for p in sorted(starters_by_pos[pos], key=lambda x: x.projected_points, reverse=True):
            rows.append(
                {
                    "Position": pos,
                    "Player": p.name,
                    "Team": p.team,
                    "Opponent": p.opponent or "",
                    "Projected": p.projected_points,
                    "Consistency (±)": p.consistency if p.consistency is not None else None,
                }
            )

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Projected": st.column_config.NumberColumn(format="%.1f"),
            "Consistency (±)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    if result.points_by_position:
        pos_df = pd.DataFrame(
            [{"Position": k, "Points": v} for k, v in sorted(result.points_by_position.items())]
        )
        fig = px.bar(
            pos_df,
            x="Position",
            y="Points",
            color="Points",
            color_continuous_scale="Blues",
            text="Points",
            title="Points Contribution by Position",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)


def _show_bench(result: LineupResult):
    """Display bench players sorted by projection."""
    if not result.bench:
        st.info("No bench players (all available players are in the starting lineup).")
        return

    rows = [
        {
            "Player": p.name,
            "Position": p.position,
            "Team": p.team,
            "Opponent": p.opponent or "",
            "Projected": p.projected_points,
        }
        for p in result.bench
    ]
    df = pd.DataFrame(rows)

    st.markdown(f"**{len(df)} bench players** (sorted by projected points, descending)")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Projected": st.column_config.NumberColumn(format="%.1f"),
        },
    )


def _show_breakdown(result: LineupResult, current_lineup):
    """Show lineup changes vs current and team distribution."""
    if result.improvement_vs_current is not None and current_lineup:
        st.markdown("### 🔄 Lineup Changes vs Your Current")

        optimal_names = {p.name for p in result.starters}
        current_names = {p.name for p in current_lineup}

        to_bench = current_names - optimal_names
        to_start = optimal_names - current_names

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**❌ Bench:**")
            if to_bench:
                for name in to_bench:
                    p = next(pl for pl in current_lineup if pl.name == name)
                    st.write(f"- {p.name} ({p.position}, {p.team}) — {p.projected_points:.1f} pts")
            else:
                st.caption("No changes needed")

        with col_b:
            st.markdown("**✅ Start:**")
            if to_start:
                for name in to_start:
                    p = next(pl for pl in result.starters if pl.name == name)
                    st.write(f"- {p.name} ({p.position}, {p.team}) — {p.projected_points:.1f} pts")
            else:
                st.caption("No changes needed")

        if not to_bench and not to_start:
            st.success("🎯 Your current lineup is already optimal!")

        st.markdown("---")

    st.markdown("### Team Distribution")
    team_counts = {}
    for p in result.starters:
        team_counts[p.team] = team_counts.get(p.team, 0) + 1

    team_df = pd.DataFrame(
        [{"Team": t, "Starters": c} for t, c in sorted(team_counts.items(), key=lambda x: -x[1])]
    )
    st.dataframe(team_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
