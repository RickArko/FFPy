"""
ESPN League Integration Example

This script demonstrates how to:
1. Connect to your ESPN Fantasy Football league
2. Get your team's roster
3. Fetch projections for your players
4. Optimize your lineup
5. Compare against your current lineup

Setup:
1. Add your ESPN credentials to .env:
   ESPN_LEAGUE_ID=123456
   ESPN_SWID={YOUR-SWID-COOKIE}  # For private leagues only
   ESPN_S2=YOUR-ESPN-S2-COOKIE    # For private leagues only

2. Run this script:
   uv run python examples/espn_league_example.py
"""

import os

from dotenv import load_dotenv

from ffpy.integrations.espn import ESPNIntegration
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.optimizer import LineupOptimizer, Player, PlayerStatus, RosterConstraints

# Load environment variables
load_dotenv()


def main():
    """Main example workflow."""

    # Step 1: Connect to your ESPN league
    print("=" * 70)
    print("ESPN LEAGUE INTEGRATION EXAMPLE")
    print("=" * 70)

    league_id = os.getenv("ESPN_LEAGUE_ID")
    if not league_id:
        print("\n⚠️  ESPN_LEAGUE_ID not found in .env file")
        print("\nTo use this example:")
        print("1. Copy .env.example to .env")
        print("2. Add your ESPN_LEAGUE_ID")
        print("3. For private leagues, add ESPN_SWID and ESPN_S2 cookies")
        print("\nSee docs/ESPN_API_INTEGRATION_GUIDE.md for details")
        return

    league_id = int(league_id)
    swid = os.getenv("ESPN_SWID", "")
    espn_s2 = os.getenv("ESPN_S2", "")

    print(f"\nConnecting to ESPN League ID: {league_id}")

    try:
        espn = ESPNLeagueIntegration(league_id=league_id, swid=swid, espn_s2=espn_s2)

        # Step 2: Get league info
        print("\n" + "=" * 70)
        print("LEAGUE INFORMATION")
        print("=" * 70)

        info = espn.get_league_info()
        print(f"League Name: {info['name']}")
        print(f"Number of Teams: {info['size']}")
        print(f"Scoring Type: {info['scoring_type']}")
        print(f"Roster Format: {info['roster_slots']}")
        print(f"Playoff Teams: {info['playoff_teams']}")

        # Step 3: Show all teams
        print("\n" + "=" * 70)
        print("ALL TEAMS")
        print("=" * 70)

        teams = espn.get_all_teams()
        for team in teams:
            record = f"{team['wins']}-{team['losses']}"
            if team["ties"] > 0:
                record += f"-{team['ties']}"
            print(f"Team {team['id']}: {team['name']:30} ({record}) - {team['points_for']:.1f} pts")

        # Step 4: Get your team's roster
        print("\n" + "=" * 70)
        print("YOUR ROSTER")
        print("=" * 70)

        # Use team ID 1 by default (change this to your team ID)
        my_team_id = int(os.getenv("ESPN_TEAM_ID", "1"))
        print(f"\nFetching roster for Team ID: {my_team_id}")
        print("(Set ESPN_TEAM_ID in .env to change this)")

        current_week = 15  # Change to current week
        roster_df = espn.get_team_roster(team_id=my_team_id, week=current_week)

        print(f"\nTotal Players: {len(roster_df)}")
        print(f"\nCurrent Lineup (Week {current_week}):")
        print("-" * 70)

        # Group by lineup slot
        starters = roster_df[roster_df["lineup_slot"] != "BENCH"]
        bench = roster_df[roster_df["lineup_slot"] == "BENCH"]

        print("\nSTARTERS:")
        for _, player in starters.iterrows():
            status = f" [{player['injury_status']}]" if player["injury_status"] != "ACTIVE" else ""
            print(
                f"  {player['lineup_slot']:8} {player['player']:25} {player['position']:3} {player['team']:3}{status}"
            )

        print(f"\nBENCH ({len(bench)} players):")
        for _, player in bench.iterrows():
            status = f" [{player['injury_status']}]" if player["injury_status"] != "ACTIVE" else ""
            print(f"  {player['player']:25} {player['position']:3} {player['team']:3}{status}")

        # Step 5: Get projections for your players
        print("\n" + "=" * 70)
        print("OPTIMIZE YOUR LINEUP")
        print("=" * 70)

        espn_api = ESPNIntegration()
        week_projections = espn_api.get_projections(week=current_week, season=2024)

        if week_projections.empty:
            print("\n⚠️  No projection data available from ESPN API")
            print("Using sample data for demonstration...")
            from ffpy.data import get_sample_projections

            week_projections = get_sample_projections()

        # Match projections to your roster
        player_names = roster_df["player"].tolist()
        my_projections = week_projections[week_projections["player"].isin(player_names)]

        if my_projections.empty:
            print("\n⚠️  Could not match projections to roster players")
            print("This might happen if player names don't match exactly")
            return

        print(f"\nFound projections for {len(my_projections)} of your {len(roster_df)} players")

        # Convert to Player objects
        players = []
        for _, row in my_projections.iterrows():
            # Check injury status from roster
            roster_player = roster_df[roster_df["player"] == row["player"]]
            status = PlayerStatus.AVAILABLE

            if not roster_player.empty:
                injury_status = roster_player.iloc[0]["injury_status"]
                if injury_status == "OUT":
                    status = PlayerStatus.OUT
                elif injury_status == "INJURED_RESERVE":
                    status = PlayerStatus.INJURED
                elif injury_status == "QUESTIONABLE":
                    status = PlayerStatus.QUESTIONABLE

            player = Player(
                name=row["player"],
                position=row["position"],
                team=row["team"],
                projected_points=row.get("projected_points", 0),
                status=status,
            )
            players.append(player)

        # Build current lineup for comparison
        current_starters = []
        for player_obj in players:
            roster_player = starters[starters["player"] == player_obj.name]
            if not roster_player.empty:
                current_starters.append(player_obj)

        # Create constraints based on league settings
        roster_slots = info["roster_slots"]
        constraints = RosterConstraints(
            positions={
                "QB": roster_slots.get("QB", 1),
                "RB": roster_slots.get("RB", 2),
                "WR": roster_slots.get("WR", 2),
                "TE": roster_slots.get("TE", 1),
                "K": roster_slots.get("K", 1),
                "D/ST": roster_slots.get("D/ST", 1),
            },
            flex_positions=["RB", "WR", "TE"],
            num_flex=roster_slots.get("FLEX", 1),
        )

        # Optimize!
        optimizer = LineupOptimizer(constraints)

        if current_starters:
            result = optimizer.optimize(players, current_lineup=current_starters)
        else:
            result = optimizer.optimize(players)

        # Show results
        print("\n" + "=" * 70)
        print("OPTIMIZATION RESULTS")
        print("=" * 70)

        print(optimizer.analyze_lineup(result))

        if result.improvement_vs_current and result.improvement_vs_current > 0.5:
            print("\n💡 RECOMMENDATION: Consider updating your lineup!")
            print("\nSuggested changes:")

            current_names = {p.name for p in current_starters}
            optimal_names = {p.name for p in result.starters}

            # Players to bench
            to_bench = current_names - optimal_names
            if to_bench:
                print("\n❌ BENCH:")
                for name in to_bench:
                    player = next(p for p in current_starters if p.name == name)
                    print(f"   {player.name} ({player.position}) - {player.projected_points:.1f} pts")

            # Players to start
            to_start = optimal_names - current_names
            if to_start:
                print("\n✅ START:")
                for name in to_start:
                    player = next(p for p in result.starters if p.name == name)
                    print(f"   {player.name} ({player.position}) - {player.projected_points:.1f} pts")
        elif result.improvement_vs_current:
            print("\n✅ Your current lineup is already optimal! No changes needed.")
        else:
            print("\nYour optimized lineup is shown above.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nPossible issues:")
        print("1. Invalid league ID")
        print("2. Private league requires ESPN_SWID and ESPN_S2 cookies")
        print("3. Invalid or expired cookies")
        print("4. Network connectivity issues")
        print("\nSee docs/ESPN_API_INTEGRATION_GUIDE.md for troubleshooting")


if __name__ == "__main__":
    main()
