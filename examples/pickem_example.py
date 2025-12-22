"""
NFL Pick'em Competition Example

This script demonstrates how to use the Pick'em Analyzer to:
1. Get weekly NFL games and matchups
2. Calculate confidence rankings for your picks
3. Identify potential upset candidates
4. Generate optimal pick strategies
5. Format picks for easy submission

Setup:
1. No API keys required! Uses ESPN's public scoreboard API
2. Run this script:
   uv run python examples/pickem_example.py
"""

from ffpy.pickem import PickemAnalyzer, create_sample_pickem_data


def main():
    """Main pick'em example workflow."""

    print("=" * 70)
    print("NFL PICK'EM ANALYZER")
    print("=" * 70)

    # Initialize analyzer for current season
    analyzer = PickemAnalyzer(season=2025)

    # Specify the week you want to analyze
    current_week = 16  # Change to current week

    print(f"\nFetching Week {current_week} NFL games...")

    # Get weekly games from ESPN API
    games = analyzer.get_weekly_games(week=current_week)

    # If no games found (off-season or API issues), use sample data
    if not games:
        print("\n" + "=" * 70)
        print("⚠️  ERROR: No games found from ESPN API")
        print("=" * 70)
        print(f"Possible reasons:")
        print(f"  - Week {current_week} hasn't been scheduled yet")
        print(f"  - Off-season (no games available)")
        print(f"  - ESPN API temporarily unavailable")
        print(f"\nUsing SAMPLE DATA for demonstration...")
        print("⚠️  NOTE: Sample data contains FICTIONAL matchups!")
        print("=" * 70 + "\n")
        games = create_sample_pickem_data(week=current_week)

    print(f"Found {len(games)} games for Week {current_week}\n")

    # =========================================================================
    # STRATEGY 1: Confidence-Based Rankings
    # =========================================================================
    print("=" * 70)
    print("STRATEGY 1: CONFIDENCE-BASED RANKINGS")
    print("=" * 70)
    print("\nRanks games by certainty of outcome.")
    print("Assign highest confidence points to most certain picks.\n")

    confidence_df = analyzer.calculate_confidence_rankings(games)

    print("Confidence Rankings:")
    print("-" * 70)
    for _, row in confidence_df.iterrows():
        confidence = int(row["confidence_points"])
        matchup = row["matchup"]
        pick = row["pick"]
        spread = row["spread"]
        score = row["confidence_score"]

        print(f"{confidence:2d} pts │ {matchup:25} → {pick:4} │ Spread: {spread:4.1f} │ Score: {score:5.1f}")

    # =========================================================================
    # STRATEGY 2: All Favorites
    # =========================================================================
    print("\n" + "=" * 70)
    print("STRATEGY 2: ALL FAVORITES (STRAIGHT UP)")
    print("=" * 70)
    print("\nPick the favorite in every game (ignoring confidence).\n")

    favorites_result = analyzer.simulate_pickem_strategy(games, strategy="favorites")

    print(f"Strategy: {favorites_result['strategy']}")
    print("-" * 70)
    for pick in favorites_result["picks"]:
        matchup = pick["matchup"]
        team = pick["pick"]
        spread = pick["spread"]
        reasoning = pick["reasoning"]

        print(f"{matchup:25} → {team:4} │ {reasoning}")

    # =========================================================================
    # UPSET CANDIDATES
    # =========================================================================
    print("\n" + "=" * 70)
    print("UPSET CANDIDATES (Close Games)")
    print("=" * 70)
    print("\nGames with spreads ≤ 3 points (potential upsets).\n")

    upsets_df = analyzer.get_upset_candidates(games, threshold=3.0)

    if not upsets_df.empty:
        print("Close Matchups:")
        print("-" * 70)
        for _, row in upsets_df.iterrows():
            matchup = row["matchup"]
            favorite = row["favorite"]
            underdog = row["underdog"]
            spread = row["spread"]
            upset_prob = row["upset_probability"]

            print(f"{matchup:25} │ Favorite: {favorite:4} (-{spread:.1f}) │ Underdog: {underdog:4} │ Upset %: {upset_prob*100:.0f}%")
    else:
        print("No close games found this week (all spreads > 3 points)")

    # =========================================================================
    # FORMATTED OUTPUT (Copy/Paste Ready)
    # =========================================================================
    print("\n" + "=" * 70)
    print("FORMATTED PICKS (Copy/Paste Ready)")
    print("=" * 70)
    print()

    formatted_picks = analyzer.format_weekly_picks(games, include_confidence=True)
    print(formatted_picks)

    # =========================================================================
    # QUICK TIPS
    # =========================================================================
    print("\n" + "=" * 70)
    print("PICK'EM STRATEGY TIPS")
    print("=" * 70)
    print("""
1. **Confidence Pools**: Use confidence rankings strategy
   - Assign highest points to safest picks (big spreads)
   - Save low confidence points for toss-ups

2. **Straight Up Pools**: Pick all favorites
   - Focus on games with largest spreads
   - Consider home field advantage

3. **Upset Specials**: Target close games strategically
   - Division rivalries tend to be closer
   - Weather can be an equalizer
   - Check injury reports before finalizing

4. **Research Beyond Spreads**:
   - Check team momentum (recent wins/losses)
   - Review injury reports (especially QB, key players)
   - Consider weather for outdoor games
   - Factor in divisional matchups (always competitive)

5. **Differentiation Strategy** (for competitive pools):
   - If most people pick favorites, consider a strategic upset pick
   - Late-season games can be unpredictable (playoff implications)
""")

    print("=" * 70)
    print("Good luck with your picks! 🏈")
    print("=" * 70)


if __name__ == "__main__":
    main()
