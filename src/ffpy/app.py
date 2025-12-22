"""Fantasy Football Point Projection Web App."""

import streamlit as st
import pandas as pd
from ffpy.data import (
    get_projections,
    get_sample_projections,
    get_positions,
    filter_by_position,
    get_top_n_players,
)
from ffpy.config import Config


def main():
    """Main entry point for the Streamlit app."""
    st.set_page_config(
        page_title="FFPy - Fantasy Football Analytics",
        page_icon="🏈",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("🏈 FFPy - Fantasy Football Analytics")
    st.markdown("**Data-driven fantasy football projections and lineup optimization**")
    st.markdown("---")

    # Sidebar for filters
    st.sidebar.header("Filters")

    # Data source selection
    st.sidebar.subheader("Data Source")

    data_source = st.sidebar.radio(
        "Projection Method",
        options=["Historical Model", "API Data", "Sample Data"],
        index=0,
        help=(
            "Historical Model: Uses actual player performance data to generate projections\n\n"
            "API Data: Fetches projections from ESPN or SportsDataIO\n\n"
            "Sample Data: Uses pre-defined mock data"
        ),
    )

    # Convert radio selection to parameters
    use_historical_model = data_source == "Historical Model"
    use_real_data = data_source == "API Data"

    week = st.sidebar.selectbox(
        "Select Week",
        options=list(range(1, 19)),
        index=0,
    )

    position = st.sidebar.selectbox(
        "Select Position",
        options=["All Positions"] + get_positions(),
        index=0,
    )

    top_n = st.sidebar.slider(
        "Number of Players to Display",
        min_value=5,
        max_value=50,
        value=10,
        step=5,
    )

    # Show data source status
    if use_historical_model:
        st.sidebar.caption("📊 Using database-driven projections")
    elif use_real_data:
        config_status = Config.debug_config()
        st.sidebar.caption(f"API: {config_status['api_provider'].upper()}")
    else:
        st.sidebar.caption("🎲 Using sample data")

    # Get projections
    projections = get_projections(
        week=week,
        use_real_data=use_real_data,
        use_historical_model=use_historical_model,
    )

    # Filter by position if selected
    if position != "All Positions":
        projections = filter_by_position(projections, position)

    # Get top N players
    top_players = get_top_n_players(projections, n=top_n)

    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Players", len(projections))
    with col2:
        st.metric("Avg Projected Points", f"{projections['projected_points'].mean():.1f}")
    with col3:
        st.metric(
            "Top Player",
            top_players.iloc[0]["player"] if len(top_players) > 0 else "N/A",
        )
    with col4:
        st.metric(
            "Top Projection",
            f"{top_players.iloc[0]['projected_points']:.1f}" if len(top_players) > 0 else "N/A",
        )

    st.markdown("---")

    # Display top players by position
    if position == "All Positions":
        st.subheader(f"Top {top_n} Players - All Positions (Week {week})")
    else:
        st.subheader(f"Top {top_n} {position}s (Week {week})")

    # Format the dataframe for display
    display_df = format_dataframe_for_display(top_players, position)

    # Display the dataframe
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "projected_points": st.column_config.NumberColumn(
                "Projected Points",
                format="%.1f",
            ),
        },
    )

    # Position breakdown
    if position == "All Positions":
        st.markdown("---")
        st.subheader("Projections by Position")

        cols = st.columns(len(get_positions()))
        for idx, pos in enumerate(get_positions()):
            with cols[idx]:
                pos_data = filter_by_position(projections, pos)
                top_pos = get_top_n_players(pos_data, n=5)

                st.markdown(f"### {pos}")
                st.dataframe(
                    top_pos[["player", "team", "projected_points"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "player": "Player",
                        "team": "Team",
                        "projected_points": st.column_config.NumberColumn(
                            "Proj Pts",
                            format="%.1f",
                        ),
                    },
                )


def format_dataframe_for_display(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """
    Format the dataframe for display in the app.

    Args:
        df: DataFrame to format
        position: Selected position filter

    Returns:
        Formatted DataFrame
    """
    # Base columns always shown
    base_cols = ["player", "team", "position", "opponent", "projected_points"]

    # Position-specific columns
    position_cols = {
        "QB": ["passing_yards", "passing_tds", "rushing_yards"],
        "RB": ["rushing_yards", "rushing_tds", "receiving_yards", "receptions"],
        "WR": ["receiving_yards", "receiving_tds", "receptions"],
        "TE": ["receiving_yards", "receiving_tds", "receptions"],
    }

    # Select columns based on position
    if position in position_cols:
        cols_to_show = base_cols + position_cols[position]
    elif position == "All Positions":
        # Show only base columns for mixed positions
        cols_to_show = base_cols
    else:
        cols_to_show = base_cols

    # Filter to available columns
    cols_to_show = [col for col in cols_to_show if col in df.columns]

    display_df = df[cols_to_show].copy()

    # Rename columns for better display
    column_renames = {
        "player": "Player",
        "team": "Team",
        "position": "Pos",
        "opponent": "Opp",
        "projected_points": "Projected Points",
        "passing_yards": "Pass Yds",
        "passing_tds": "Pass TDs",
        "rushing_yards": "Rush Yds",
        "rushing_tds": "Rush TDs",
        "receiving_yards": "Rec Yds",
        "receiving_tds": "Rec TDs",
        "receptions": "Rec",
    }

    display_df = display_df.rename(
        columns={k: v for k, v in column_renames.items() if k in display_df.columns}
    )

    return display_df


if __name__ == "__main__":
    main()
