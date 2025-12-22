"""
NFL Pick'em Competition Analyzer

Interactive tool for analyzing NFL games and generating optimal pick'em strategies.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from ffpy.pickem import PickemAnalyzer, create_sample_pickem_data, NFLGame


# Page config
st.set_page_config(page_title="Pick'em Analyzer", page_icon="🏈", layout="wide")

st.title("🏈 NFL Pick'em Competition Analyzer")
st.markdown("""
Analyze weekly NFL matchups and generate optimal picking strategies for:
- **Confidence Pools** (assign confidence points 1-N to each pick)
- **Straight Up Pools** (pick winners, no confidence)
- **Upset Specials** (identify potential upsets)
""")

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

season = st.sidebar.number_input(
    "Season", min_value=2020, max_value=2025, value=2025, step=1, help="Current NFL season (2025)"
)

week = st.sidebar.number_input(
    "Week", min_value=1, max_value=18, value=16, step=1, help="NFL regular season week (1-18)"
)

use_sample_data = st.sidebar.checkbox(
    "Use Sample Data", value=False, help="Use sample data instead of fetching from ESPN API"
)

upset_threshold = st.sidebar.slider(
    "Upset Threshold (pts)",
    min_value=1.0,
    max_value=7.0,
    value=3.0,
    step=0.5,
    help="Games with spreads below this are considered potential upsets",
)

# Initialize analyzer
analyzer = PickemAnalyzer(season=season)


# Fetch games
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_games(week_num, use_sample, season_year):
    if use_sample:
        st.warning("⚠️ Using SAMPLE DATA with fictional matchups (not real games!)")
        return create_sample_pickem_data(week=week_num)
    else:
        analyzer_temp = PickemAnalyzer(season=season_year)
        games = analyzer_temp.get_weekly_games(week=week_num)
        if not games:
            st.error(f"❌ No games found for Week {week_num}, {season_year}. Check if week number is valid.")
            st.info("💡 Try enabling 'Use Sample Data' in the sidebar to see a demo.")
            return []
        return games


with st.spinner("Fetching NFL games..."):
    games = get_games(week, use_sample_data, season)

if not games:
    st.error("❌ No games found for this week. Try a different week or use sample data.")
    st.stop()

st.success(f"✅ Loaded {len(games)} games for Week {week}, {season} season")

# Create tabs for different analyses
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Confidence Rankings", "🎯 Straight Picks", "⚡ Upset Candidates", "📈 Analytics"]
)

# ============================================================================
# TAB 1: Confidence Rankings
# ============================================================================
with tab1:
    st.header("Confidence-Based Rankings")
    st.markdown("""
    Ranks games by certainty of outcome. Assign your **highest confidence points** to the most certain picks.

    **Confidence Score** combines:
    - Point spread magnitude (60% weight)
    - Win probability (40% weight)
    """)

    confidence_df = analyzer.calculate_confidence_rankings(games)

    # Display table
    st.subheader("📋 Your Picks (Ranked by Confidence)")

    display_df = confidence_df[
        ["confidence_points", "matchup", "pick", "spread", "win_prob", "confidence_score"]
    ].copy()

    display_df.columns = ["Confidence", "Matchup", "Pick", "Spread", "Win Prob", "Score"]
    display_df["Spread"] = display_df["Spread"].apply(lambda x: f"{x:.1f}")
    display_df["Win Prob"] = display_df["Win Prob"].apply(
        lambda x: f"{x * 100:.0f}%" if pd.notna(x) else "N/A"
    )
    display_df["Score"] = display_df["Score"].apply(lambda x: f"{x:.1f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Visualization: Confidence scores
    st.subheader("📊 Confidence Score Distribution")

    fig = px.bar(
        confidence_df,
        x="matchup",
        y="confidence_score",
        color="confidence_score",
        color_continuous_scale="RdYlGn",
        labels={"confidence_score": "Confidence Score", "matchup": "Matchup"},
        hover_data=["pick", "spread", "confidence_points"],
    )

    fig.update_layout(xaxis_tickangle=-45, height=400, showlegend=False)

    st.plotly_chart(fig, use_container_width=True)

    # Copy/paste formatted output
    st.subheader("📋 Copy/Paste Output")
    formatted = analyzer.format_weekly_picks(games, include_confidence=True)
    st.code(formatted, language="text")

# ============================================================================
# TAB 2: Straight Picks
# ============================================================================
with tab2:
    st.header("Straight Up Picks (All Favorites)")
    st.markdown("""
    Pick the **favorite in every game** based on point spreads.
    Use this for pools that don't use confidence points.
    """)

    favorites_result = analyzer.simulate_pickem_strategy(games, strategy="favorites")

    picks_data = []
    for pick in favorites_result["picks"]:
        picks_data.append(
            {
                "Matchup": pick["matchup"],
                "Pick": pick["pick"],
                "Spread": f"{pick['spread']:.1f}",
                "Reasoning": pick["reasoning"],
            }
        )

    picks_df = pd.DataFrame(picks_data)

    st.dataframe(picks_df, use_container_width=True, hide_index=True)

    # Summary stats
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Games", len(picks_data))

    with col2:
        avg_spread = sum([float(p["Spread"]) for p in picks_data]) / len(picks_data)
        st.metric("Avg Spread", f"{avg_spread:.1f} pts")

    with col3:
        large_favorites = len([p for p in picks_data if float(p["Spread"]) >= 7.0])
        st.metric("Large Favorites (≥7)", large_favorites)

    # Spread distribution
    st.subheader("📊 Spread Distribution")

    spreads = [float(p["Spread"]) for p in picks_data]
    fig = px.histogram(
        x=spreads,
        nbins=15,
        labels={"x": "Point Spread", "y": "Number of Games"},
        color_discrete_sequence=["#1f77b4"],
    )

    fig.update_layout(showlegend=False, height=350)

    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 3: Upset Candidates
# ============================================================================
with tab3:
    st.header("⚡ Potential Upset Games")
    st.markdown(f"""
    Games with spreads **≤ {upset_threshold:.1f} points** are considered toss-ups.
    These are your best opportunities for:
    - Picking the underdog strategically
    - Differentiating from the crowd
    - Low-confidence assignments
    """)

    upsets_df = analyzer.get_upset_candidates(games, threshold=upset_threshold)

    if upsets_df.empty:
        st.info(f"ℹ️ No close games found this week (all spreads > {upset_threshold:.1f} points)")
    else:
        st.subheader(f"🎯 Close Matchups ({len(upsets_df)} games)")

        display_upsets = upsets_df.copy()
        display_upsets["spread"] = display_upsets["spread"].apply(lambda x: f"{x:.1f}")
        display_upsets["upset_probability"] = display_upsets["upset_probability"].apply(
            lambda x: f"{x * 100:.0f}%"
        )

        display_upsets.columns = ["Matchup", "Favorite", "Underdog", "Spread", "Upset %"]

        st.dataframe(display_upsets, use_container_width=True, hide_index=True)

        # Upset probability chart
        st.subheader("📊 Upset Probability by Game")

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=upsets_df["matchup"],
                y=upsets_df["upset_probability"] * 100,
                text=upsets_df["upset_probability"].apply(lambda x: f"{x * 100:.0f}%"),
                textposition="outside",
                marker_color="#ff7f0e",
                name="Upset Probability",
            )
        )

        fig.update_layout(
            xaxis_title="Matchup",
            yaxis_title="Upset Probability (%)",
            xaxis_tickangle=-45,
            height=400,
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Strategy recommendation
        st.info("""
        **💡 Strategy Tip**: In competitive pools, picking one or two strategic upsets can give you an edge
        if most participants pick all favorites. Consider:
        - Division rivalries (teams know each other well)
        - Home underdogs (home field advantage)
        - Weather conditions (can be an equalizer)
        - Recent momentum (check last 3 games)
        """)

# ============================================================================
# TAB 4: Analytics
# ============================================================================
with tab4:
    st.header("📈 Week Analytics")

    # Calculate statistics
    confidence_df = analyzer.calculate_confidence_rankings(games)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Game Statistics")

        total_games = len(games)
        avg_spread = confidence_df["spread"].mean()
        max_spread = confidence_df["spread"].max()
        min_spread = confidence_df["spread"].min()

        st.metric("Total Games", total_games)
        st.metric("Average Spread", f"{avg_spread:.1f} pts")
        st.metric("Largest Spread", f"{max_spread:.1f} pts")
        st.metric("Smallest Spread", f"{min_spread:.1f} pts")

        # Games by confidence tier
        st.subheader("🎯 Games by Confidence Tier")

        tiers = []
        for _, row in confidence_df.iterrows():
            spread = row["spread"]
            if spread >= 7:
                tier = "High (≥7)"
            elif spread >= 3:
                tier = "Medium (3-7)"
            else:
                tier = "Low (<3)"
            tiers.append(tier)

        tier_counts = pd.Series(tiers).value_counts()

        fig = px.pie(
            values=tier_counts.values,
            names=tier_counts.index,
            color_discrete_sequence=["#2ca02c", "#ff7f0e", "#d62728"],
        )

        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=350)

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("🏆 Top Picks")

        top_5 = confidence_df.head(5)

        st.markdown("**Most Confident Picks:**")
        for idx, row in top_5.iterrows():
            confidence = int(row["confidence_points"])
            pick = row["pick"]
            matchup = row["matchup"]
            spread = row["spread"]

            st.markdown(f"**{confidence}.** {pick} ({matchup}) - Spread: {spread:.1f}")

        st.markdown("---")

        # Win probability distribution (if available)
        if confidence_df["win_prob"].notna().sum() > 0:
            st.subheader("📊 Win Probability Distribution")

            win_probs = confidence_df[confidence_df["win_prob"].notna()]["win_prob"] * 100

            fig = px.box(
                y=win_probs, labels={"y": "Win Probability (%)"}, color_discrete_sequence=["#9467bd"]
            )

            fig.update_layout(showlegend=False, height=300)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("ℹ️ Win probability data not available for this week")

    # Game details table
    st.subheader("🏈 All Games Details")

    details_data = []
    for game in games:
        favorite, spread = game.get_favorite()
        underdog = game.away_abbrev if favorite == game.home_abbrev else game.home_abbrev

        details_data.append(
            {
                "Matchup": f"{game.away_abbrev} @ {game.home_abbrev}",
                "Favorite": favorite,
                "Underdog": underdog,
                "Spread": f"{spread:.1f}",
                "O/U": f"{game.over_under:.1f}" if game.over_under else "N/A",
                "Win Prob": f"{game.home_win_prob * 100:.0f}%" if game.home_win_prob else "N/A",
                "Status": "Final" if game.is_final else "Upcoming",
                "Time": game.game_time.strftime("%a %I:%M %p") if game.game_time else "TBD",
            }
        )

    details_df = pd.DataFrame(details_data)

    st.dataframe(details_df, use_container_width=True, hide_index=True)

# Footer
st.markdown("---")
st.markdown("""
**🏈 Pick'em Strategy Resources:**
- Check injury reports before finalizing picks
- Consider weather for outdoor games
- Division games are often closer than spreads suggest
- Late-season games can be unpredictable (playoff implications)
- Differentiate strategically in competitive pools
""")
