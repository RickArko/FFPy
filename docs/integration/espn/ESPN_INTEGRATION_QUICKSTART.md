# ESPN Integration - Quick Start Guide

## What You Can Do Now

✅ **Get general ESPN projections** (no auth required)
✅ **Access your ESPN league** (requires league ID + cookies)
✅ **Import your roster** automatically
✅ **Optimize your lineup** based on your actual roster
✅ **Compare vs current lineup** to see improvements

## Quick Setup (5 minutes)

### Step 1: Find Your League ID

1. Go to your ESPN Fantasy Football league
2. Look at the URL: `https://fantasy.espn.com/football/league?leagueId=123456`
3. Your League ID is `123456`

### Step 2: Get Cookies (Private Leagues Only)

**Skip this if your league is PUBLIC**

For PRIVATE leagues:

1. Open browser DevTools (Press F12)
2. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
3. Expand **Cookies** → `https://www.espn.com`
4. Find and copy these two values:
   - `swid` - looks like `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`
   - `espn_s2` - long string (~200 characters)

### Step 3: Add to .env

```bash
# Add these lines to your .env file
ESPN_LEAGUE_ID=123456
ESPN_TEAM_ID=1  # Your team ID (usually 1-12)

# For private leagues only:
ESPN_SWID={YOUR-SWID-HERE}
ESPN_S2=YOUR-ESPN-S2-HERE
```

### Step 4: Test It!

```bash
uv run python examples/espn_league_example.py
```

## Usage Examples

### Example 1: View Your Roster

```python
from ffpy.integrations.espn_league import ESPNLeagueIntegration

espn = ESPNLeagueIntegration(league_id=123456)

# Get your roster
roster = espn.get_team_roster(team_id=1, week=15)

print(roster[['player', 'position', 'lineup_slot', 'injury_status']])
```

Output:
```
                  player position lineup_slot injury_status
0      Patrick Mahomes       QB          QB        ACTIVE
1  Christian McCaffrey       RB          RB        ACTIVE
2       Austin Ekeler       RB          RB        ACTIVE
...
```

### Example 2: Get League Standings

```python
standings = espn.get_standings()

print(standings)
```

Output:
```
rank              name  wins  losses  ties  points_for  points_against
   1      Team Alpha     9       3     0     1245.6          1123.2
   2       Team Beta     8       4     0     1198.3          1156.8
...
```

### Example 3: Optimize Your Lineup

```python
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.integrations.espn import ESPNIntegration
from ffpy.optimizer import LineupOptimizer, RosterConstraints, Player

# Get your roster
espn_league = ESPNLeagueIntegration(league_id=123456)
roster = espn_league.get_team_roster(team_id=1, week=15)

# Get projections
espn_api = ESPNIntegration()
projections = espn_api.get_projections(week=15)

# Match projections to your roster players
my_players = projections[projections['player'].isin(roster['player'])]

# Convert to Player objects
players = [
    Player(row['player'], row['position'], row['team'], row['projected_points'])
    for _, row in my_players.iterrows()
]

# Optimize
constraints = RosterConstraints.standard()
optimizer = LineupOptimizer(constraints)
result = optimizer.optimize(players)

print(f"Optimal lineup: {result.total_points:.1f} projected points")
```

### Example 4: Compare All Teams

```python
# Get all rosters
rosters = espn.get_league_rosters(week=15)

# Get projections
projections = espn_api.get_projections(week=15)

# Optimize each team
for team_id, roster in rosters.items():
    team_players = projections[projections['player'].isin(roster['player'])]
    # ... optimize and compare
```

## Available Methods

### ESPNLeagueIntegration

```python
espn = ESPNLeagueIntegration(league_id, season=2024, swid=None, espn_s2=None)

# League info
espn.get_league_info()  # Name, size, scoring, settings

# Teams
espn.get_all_teams()  # All teams with records

# Rosters
espn.get_team_roster(team_id, week)  # One team's roster
espn.get_league_rosters(week)  # All teams' rosters

# Competition
espn.get_standings()  # Current standings
espn.get_matchups(week)  # Week's matchups

# Settings
espn.get_scoring_settings()  # League scoring rules
```

### ESPNIntegration (Public API)

```python
espn = ESPNIntegration()

# General player data (no league needed)
espn.get_projections(week, season)  # All player projections
espn.get_actual_stats(week, season)  # Actual performance
```

## Common Workflows

### Workflow 1: Weekly Lineup Check

```bash
# Every Tuesday before waivers
uv run python examples/espn_league_example.py

# See:
# - Your current lineup
# - Optimal lineup
# - Suggested changes
# - Point improvement
```

### Workflow 2: Trade Evaluation

```python
# Compare your player vs their player
your_player = projections[projections['player'] == 'Player A']
their_player = projections[projections['player'] == 'Player B']

# See rest-of-season outlook
# Check scoring format impact
# Evaluate position needs
```

### Workflow 3: Waiver Priority

```python
# Get available free agents
all_players = espn_api.get_projections(week=15)
rostered = roster['player'].tolist()
free_agents = all_players[~all_players['player'].isin(rostered)]

# Sort by projection
top_fa = free_agents.nlargest(20, 'projected_points')

# Compare to your bench
bench = roster[roster['lineup_slot'] == 'BENCH']
# ... decide who to drop
```

## Troubleshooting

### Error: 401 Unauthorized
**Fix:** Refresh your cookies (they expire periodically)

### Error: Team not found
**Fix:** Check team ID with `espn.get_all_teams()`

### Error: No projection data
**Fix:** ESPN API may be down, use historical model instead:
```python
from ffpy.projections import HistoricalProjectionModel
model = HistoricalProjectionModel()
projections = model.generate_projections(season=2024, week=15)
```

### Error: Player name mismatch
**Fix:** ESPN uses full names, some datasets use abbreviations:
```python
# Fuzzy matching
from fuzzywuzzy import fuzz
for roster_player in roster_names:
    best_match = max(
        projection_names,
        key=lambda x: fuzz.ratio(roster_player, x)
    )
```

## Security Notes

⚠️ **NEVER commit .env to git**
⚠️ **Don't share your cookies publicly**
⚠️ **Cookies expire - refresh periodically**
✅ **Use environment variables in production**

## Next Steps

1. ✅ Run the example script
2. ✅ Verify your roster loads correctly
3. ✅ Check optimization results
4. 🚀 Integrate into Streamlit UI
5. 🚀 Build automated weekly analysis
6. 🚀 Create league-wide power rankings

See `docs/ESPN_API_INTEGRATION_GUIDE.md` for advanced usage!
