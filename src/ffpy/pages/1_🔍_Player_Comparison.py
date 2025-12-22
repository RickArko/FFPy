"""
Player Comparison - Compare multiple players side-by-side.

This page allows you to select and compare multiple fantasy football players
across various metrics including projections, historical performance, consistency,
and scoring systems.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict

from ffpy.data import get_projections, get_positions
from ffpy.database import FFPyDatabase
from ffpy.scoring import ScoringConfig, calculate_fantasy_points
from ffpy.config import Config


def main():
    """Main entry point for player comparison page."""
    st.set_page_config(
        page_title="Player Comparison - FFPy",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 Player Comparison")
    st.markdown("Compare multiple players side-by-side across projections, historical performance, and scoring systems")
    st.markdown("---")

    # Sidebar for player selection
    with st.sidebar:
        st.header("Player Selection")

        # Week selection
        week = st.selectbox(
            "Week",
            options=list(range(1, 19)),
            index=14,  # Default to week 15
            help="Select the week for projections"
        )

        # Position filter
        position_filter = st.selectbox(
            "Filter by Position",
            options=["All"] + get_positions(),
            index=0,
            help="Filter available players by position"
        )

        # Data source
        data_source = st.radio(
            "Data Source",
            options=["Historical Model", "Sample Data"],
            index=0,
            help="Historical Model uses database projections, Sample uses mock data"
        )

    # Load player data
    use_historical = data_source == "Historical Model"
    projections = get_projections(
        week=week,
        use_real_data=False,
        use_historical_model=use_historical
    )

    if projections.empty:
        st.warning("No projection data available. Using sample data.")
        projections = get_projections(week=week, use_real_data=False, use_historical_model=False)

    # Filter by position if selected
    if position_filter != "All":
        projections = projections[projections["position"] == position_filter]

    # Player multi-select
    with st.sidebar:
        st.subheader("Select Players to Compare")

        # Create player labels with position and projected points
        player_labels = []
        player_map = {}
        player_projections = {}

        for _, row in projections.iterrows():
            label = f"{row['player']} ({row['position']}, {row['team']}) - {row['projected_points']:.1f} pts"
            player_labels.append(label)
            player_map[label] = row['player']
            player_projections[label] = row['projected_points']

        # Sort by projected points (descending)
        player_labels.sort(key=lambda x: player_projections[x], reverse=True)

        selected_labels = st.multiselect(
            "Players (max 6)",
            options=player_labels,
            default=player_labels[:3] if len(player_labels) >= 3 else player_labels,
            max_selections=6,
            help="Select 2-6 players to compare"
        )

        selected_players = [player_map[label] for label in selected_labels]

    # Check if players are selected
    if not selected_players:
        st.info("👈 Select at least 1 player from the sidebar to begin comparison")
        return

    if len(selected_players) == 1:
        st.info("Select at least 2 players for a meaningful comparison")

    # Filter projections to selected players
    comparison_data = projections[projections["player"].isin(selected_players)].copy()

    # Display comparison sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Projections",
        "📈 Historical Performance",
        "⚖️ Scoring Systems",
        "📋 Stats Breakdown"
    ])

    with tab1:
        show_projections_comparison(comparison_data, week)

    with tab2:
        show_historical_performance(selected_players, week)

    with tab3:
        show_scoring_system_comparison(comparison_data)

    with tab4:
        show_stats_breakdown(comparison_data)


def show_projections_comparison(data: pd.DataFrame, week: int):
    """Display projected points comparison."""
    st.subheader(f"Week {week} Projections")

    if data.empty:
        st.warning("No projection data available")
        return

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Highest Projection",
            f"{data['projected_points'].max():.1f} pts",
            data.loc[data['projected_points'].idxmax(), 'player']
        )
    with col2:
        st.metric(
            "Average Projection",
            f"{data['projected_points'].mean():.1f} pts"
        )
    with col3:
        if 'consistency' in data.columns:
            most_consistent_idx = data['consistency'].idxmin()
            st.metric(
                "Most Consistent",
                data.loc[most_consistent_idx, 'player'],
                f"±{data.loc[most_consistent_idx, 'consistency']:.1f} pts"
            )

    st.markdown("---")

    # Projected points bar chart
    fig = px.bar(
        data.sort_values('projected_points', ascending=True),
        y='player',
        x='projected_points',
        orientation='h',
        color='projected_points',
        color_continuous_scale='Blues',
        title="Projected Fantasy Points",
        labels={'projected_points': 'Projected Points', 'player': 'Player'}
    )

    fig.update_layout(
        height=max(300, len(data) * 80),
        showlegend=False,
        yaxis={'categoryorder': 'total ascending'}
    )

    st.plotly_chart(fig, use_container_width=True)

    # Consistency visualization (if available)
    if 'consistency' in data.columns:
        st.markdown("### Consistency (Lower is Better)")

        fig_consistency = px.bar(
            data.sort_values('consistency', ascending=False),
            y='player',
            x='consistency',
            orientation='h',
            color='consistency',
            color_continuous_scale='Reds_r',
            title="Point Variance (Standard Deviation)",
            labels={'consistency': 'Std Dev (pts)', 'player': 'Player'}
        )

        fig_consistency.update_layout(
            height=max(300, len(data) * 80),
            showlegend=False,
            yaxis={'categoryorder': 'total descending'}
        )

        st.plotly_chart(fig_consistency, use_container_width=True)

    # Detailed comparison table
    st.markdown("### Detailed Comparison")

    display_cols = ['player', 'team', 'position', 'opponent', 'projected_points']
    if 'consistency' in data.columns:
        display_cols.append('consistency')

    display_cols = [col for col in display_cols if col in data.columns]

    display_df = data[display_cols].copy()
    display_df = display_df.rename(columns={
        'player': 'Player',
        'team': 'Team',
        'position': 'Position',
        'opponent': 'Opponent',
        'projected_points': 'Projected Points',
        'consistency': 'Consistency (±)'
    })

    st.dataframe(
        display_df.sort_values('Projected Points', ascending=False),
        use_container_width=True,
        hide_index=True
    )


def show_historical_performance(players: List[str], current_week: int):
    """Display historical performance trends."""
    st.subheader("Historical Performance (Last 8 Weeks)")

    try:
        db = FFPyDatabase()

        # Collect historical data for each player
        historical_data = []

        for player_name in players:
            player_history = db.get_player_history(player_name, num_weeks=8)

            if not player_history.empty:
                player_history['player'] = player_name
                historical_data.append(player_history)

        db.close()

        if not historical_data:
            st.info("No historical data available in database. Try using sample data or collect stats first.")
            return

        # Combine all player data
        all_history = pd.concat(historical_data, ignore_index=True)

        # Performance trend line chart
        fig = px.line(
            all_history,
            x='week',
            y='actual_points',
            color='player',
            markers=True,
            title="Fantasy Points by Week",
            labels={'week': 'Week', 'actual_points': 'Fantasy Points', 'player': 'Player'}
        )

        fig.update_layout(
            height=500,
            hovermode='x unified',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        st.plotly_chart(fig, use_container_width=True)

        # Summary statistics
        st.markdown("### Performance Summary")

        summary_stats = []
        for player_name in players:
            player_data = all_history[all_history['player'] == player_name]

            if not player_data.empty:
                summary_stats.append({
                    'Player': player_name,
                    'Games': len(player_data),
                    'Avg Points': player_data['actual_points'].mean(),
                    'High': player_data['actual_points'].max(),
                    'Low': player_data['actual_points'].min(),
                    'Std Dev': player_data['actual_points'].std()
                })

        summary_df = pd.DataFrame(summary_stats)
        summary_df = summary_df.round(1)

        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Error loading historical data: {e}")
        st.info("Make sure you have collected historical stats using the data collection scripts.")


def show_scoring_system_comparison(data: pd.DataFrame):
    """Compare players across different scoring systems."""
    st.subheader("Scoring System Comparison")
    st.markdown("See how player rankings change under different scoring rules")

    if data.empty:
        st.warning("No data available")
        return

    # Define scoring systems
    scoring_systems = {
        'PPR': ScoringConfig.ppr(),
        'Half-PPR': ScoringConfig.half_ppr(),
        'Standard': ScoringConfig.standard()
    }

    # Calculate points under each system
    results = []

    for system_name, config in scoring_systems.items():
        for _, player_row in data.iterrows():
            # Extract stats
            stats = {
                'passing_yards': player_row.get('passing_yards', 0),
                'passing_tds': player_row.get('passing_tds', 0),
                'interceptions': player_row.get('interceptions', 0),
                'rushing_yards': player_row.get('rushing_yards', 0),
                'rushing_tds': player_row.get('rushing_tds', 0),
                'receiving_yards': player_row.get('receiving_yards', 0),
                'receiving_tds': player_row.get('receiving_tds', 0),
                'receptions': player_row.get('receptions', 0)
            }

            points = calculate_fantasy_points(stats, config)

            results.append({
                'Player': player_row['player'],
                'Position': player_row['position'],
                'Scoring System': system_name,
                'Points': points
            })

    results_df = pd.DataFrame(results)

    # Grouped bar chart
    fig = px.bar(
        results_df,
        x='Player',
        y='Points',
        color='Scoring System',
        barmode='group',
        title="Fantasy Points by Scoring System",
        color_discrete_map={
            'PPR': '#1f77b4',
            'Half-PPR': '#ff7f0e',
            'Standard': '#2ca02c'
        }
    )

    fig.update_layout(
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show ranking changes
    st.markdown("### Rankings by Scoring System")

    col1, col2, col3 = st.columns(3)

    for idx, (system_name, col) in enumerate(zip(scoring_systems.keys(), [col1, col2, col3])):
        with col:
            st.markdown(f"**{system_name}**")

            system_data = results_df[results_df['Scoring System'] == system_name].copy()
            system_data = system_data.sort_values('Points', ascending=False)
            system_data['Rank'] = range(1, len(system_data) + 1)

            display_df = system_data[['Rank', 'Player', 'Points']].copy()
            display_df['Points'] = display_df['Points'].round(1)

            st.dataframe(display_df, use_container_width=True, hide_index=True, height=250)

    # Impact of receptions (for pass-catchers)
    reception_impact = results_df.pivot_table(
        index='Player',
        columns='Scoring System',
        values='Points'
    )

    if 'PPR' in reception_impact.columns and 'Standard' in reception_impact.columns:
        reception_impact['PPR Bonus'] = reception_impact['PPR'] - reception_impact['Standard']

        st.markdown("### PPR Impact")
        st.markdown("Points gained from PPR scoring vs Standard")

        impact_df = reception_impact[['PPR Bonus']].sort_values('PPR Bonus', ascending=False)
        impact_df = impact_df.reset_index()
        impact_df['PPR Bonus'] = impact_df['PPR Bonus'].round(1)

        st.dataframe(impact_df, use_container_width=True, hide_index=True)


def show_stats_breakdown(data: pd.DataFrame):
    """Display detailed statistical breakdown."""
    st.subheader("Statistical Breakdown")

    if data.empty:
        st.warning("No data available")
        return

    # Position-specific stats
    positions = data['position'].unique()

    for position in positions:
        pos_data = data[data['position'] == position].copy()

        st.markdown(f"### {position} Stats")

        # Determine relevant stats by position
        if position == 'QB':
            stat_cols = ['passing_yards', 'passing_tds', 'rushing_yards', 'rushing_tds']
            stat_labels = ['Pass Yds', 'Pass TDs', 'Rush Yds', 'Rush TDs']
        elif position == 'RB':
            stat_cols = ['rushing_yards', 'rushing_tds', 'receiving_yards', 'receptions']
            stat_labels = ['Rush Yds', 'Rush TDs', 'Rec Yds', 'Receptions']
        elif position in ['WR', 'TE']:
            stat_cols = ['receiving_yards', 'receiving_tds', 'receptions']
            stat_labels = ['Rec Yds', 'Rec TDs', 'Receptions']
        else:
            continue

        # Filter to available columns
        available_stats = [col for col in stat_cols if col in pos_data.columns]
        available_labels = [stat_labels[stat_cols.index(col)] for col in available_stats]

        if not available_stats:
            st.info(f"No detailed stats available for {position}")
            continue

        # Create grouped bar chart for stats
        stats_data = []
        for _, player_row in pos_data.iterrows():
            for stat_col, stat_label in zip(available_stats, available_labels):
                stats_data.append({
                    'Player': player_row['player'],
                    'Stat': stat_label,
                    'Value': player_row.get(stat_col, 0)
                })

        stats_df = pd.DataFrame(stats_data)

        fig = px.bar(
            stats_df,
            x='Stat',
            y='Value',
            color='Player',
            barmode='group',
            title=f"{position} Statistical Comparison"
        )

        fig.update_layout(height=400)

        st.plotly_chart(fig, use_container_width=True)

        # Detailed stats table
        display_cols = ['player', 'team'] + available_stats + ['projected_points']
        display_df = pos_data[display_cols].copy()

        # Rename columns
        rename_map = {
            'player': 'Player',
            'team': 'Team',
            'projected_points': 'Projected Points'
        }
        rename_map.update(dict(zip(available_stats, available_labels)))

        display_df = display_df.rename(columns=rename_map)

        st.dataframe(
            display_df.sort_values('Projected Points', ascending=False),
            use_container_width=True,
            hide_index=True
        )


if __name__ == "__main__":
    main()
