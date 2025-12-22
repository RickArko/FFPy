# ESPN Fantasy Football API Integration Guide

## Overview

ESPN provides an unofficial Fantasy Football API that allows you to access:
- ✅ **Public data** (player projections, stats) - No auth required
- ✅ **Private league data** (rosters, lineups, standings) - Requires cookies

## What's Already Implemented

The existing `ESPNIntegration` class (`src/ffpy/integrations/espn.py`) provides:

```python
from ffpy.integrations.espn import ESPNIntegration

espn = ESPNIntegration()

# Get player projections for a week
projections = espn.get_projections(week=15, season=2024)

# Get actual stats for a week
actuals = espn.get_actual_stats(week=14, season=2024)
```

**This works without authentication** and gives you general NFL player data.

## Accessing Your ESPN League (Private Data)

To access **your specific league's rosters**, you need authentication cookies.

### Step 1: Get Your League ID

1. Log into ESPN Fantasy Football
2. Go to your league homepage
3. Look at the URL: `https://fantasy.espn.com/football/league?leagueId=123456`
4. Your League ID is `123456`

### Step 2: Get Authentication Cookies (Private Leagues Only)

**If your league is PUBLIC**, skip to Step 3.

**If your league is PRIVATE**, you need two cookies:

#### Option A: Browser DevTools (Easy)

1. Log into ESPN Fantasy Football
2. Open browser DevTools (F12)
3. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Click **Cookies** → `https://www.espn.com`
5. Find these two cookies:
   - `swid` (looks like `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`)
   - `espn_s2` (long string, ~200 characters)
6. Copy both values

#### Option B: Using curl (Advanced)

```bash
# After logging in, get cookies from curl
curl -c cookies.txt https://fantasy.espn.com/football/league?leagueId=YOUR_LEAGUE_ID

# Extract swid and espn_s2 from cookies.txt
```

### Step 3: Store Credentials in .env

Add to your `.env` file:

```bash
# ESPN League Integration
ESPN_LEAGUE_ID=123456
ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
ESPN_S2=AEBxyz...long_string_here...xyz
```

**Security Note:** Never commit `.env` to git! It's already in `.gitignore`.

## Enhanced ESPN Integration (League Access)

I'll create an enhanced module that accesses your league data:

### Features to Add

```python
# Get your team's roster
my_roster = espn.get_team_roster(team_id=1)

# Get all league rosters
all_rosters = espn.get_league_rosters()

# Get current lineups (starters vs bench)
lineups = espn.get_lineups(week=15)

# Get league settings (scoring, roster positions)
settings = espn.get_league_settings()

# Get standings
standings = espn.get_standings()

# Get matchups for a week
matchups = espn.get_matchups(week=15)
```

## ESPN API Endpoints Reference

### Public Endpoints (No Auth)

**General Player Data:**
```
GET https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leaguedefaults/3
Params: scoringPeriodId={week}, view=kona_player_info
```

### Private Endpoints (Requires Cookies)

**League Data:**
```
GET https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{leagueId}
Params: view=mRoster (rosters)
       view=mTeam (teams)
       view=mSettings (league settings)
       view=mMatchup (matchups)
       view=mStandings (standings)
Headers: Cookie: swid={swid}; espn_s2={espn_s2}
```

**Multiple Views:**
```
# Get multiple views at once
Params: view=mRoster&view=mMatchup&view=mSettings
```

## Example: Full Integration

```python
from ffpy.integrations.espn import ESPNLeagueIntegration
from ffpy.optimizer import Player, LineupOptimizer, RosterConstraints
from ffpy.scoring import ScoringConfig

# Initialize with your league
espn = ESPNLeagueIntegration(
    league_id=123456,
    swid="{YOUR-SWID}",
    espn_s2="YOUR_ESPN_S2_COOKIE"
)

# Get your team's roster
my_team_id = 1  # Your team ID
roster = espn.get_team_roster(team_id=my_team_id, week=15)

# Get projections for your players
projections = espn.get_projections_for_roster(roster, week=15)

# Convert to Player objects for optimizer
players = []
for _, row in projections.iterrows():
    player = Player(
        name=row['player'],
        position=row['position'],
        team=row['team'],
        projected_points=row['projected_points']
    )
    players.append(player)

# Optimize lineup
constraints = RosterConstraints.from_espn_league(espn)  # Auto-detect league format
optimizer = LineupOptimizer(constraints)
result = optimizer.optimize(players)

# Compare to your current lineup
current_lineup = espn.get_current_lineup(team_id=my_team_id, week=15)
result_with_improvement = optimizer.optimize(players, current_lineup=current_lineup)

print(f"Your lineup: {sum(p.projected_points for p in current_lineup):.1f} pts")
print(f"Optimal lineup: {result.total_points:.1f} pts")
print(f"Improvement: {result.improvement_vs_current:+.1f} pts")
```

## ESPN Data Structures

### Roster Response
```json
{
  "teams": [{
    "id": 1,
    "name": "Team Name",
    "roster": {
      "entries": [{
        "playerId": 12345,
        "playerPoolEntry": {
          "player": {
            "fullName": "Patrick Mahomes",
            "defaultPositionId": 1,
            "proTeamId": 12
          }
        },
        "lineupSlotId": 0  // 0=QB, 2=RB, 4=WR, etc.
      }]
    }
  }]
}
```

### Lineup Slot IDs
```python
LINEUP_SLOTS = {
    0: "QB",
    2: "RB",
    4: "WR",
    6: "TE",
    16: "D/ST",
    17: "K",
    20: "BENCH",
    21: "IR",
    23: "FLEX"
}
```

### Scoring Period vs Week

ESPN uses `scoringPeriodId` which maps to NFL weeks:
- Week 1 = scoringPeriodId 1
- Week 18 = scoringPeriodId 18
- Playoffs continue with 19, 20, 21...

## Common Issues & Solutions

### Issue: 401 Unauthorized
**Cause:** Invalid or expired cookies
**Solution:** Re-authenticate and get fresh `swid` and `espn_s2` cookies

### Issue: Empty roster data
**Cause:** Wrong team ID or week
**Solution:**
```python
# List all teams to find your ID
teams = espn.get_all_teams()
for team in teams:
    print(f"Team {team['id']}: {team['name']}")
```

### Issue: Rate limiting
**Cause:** Too many requests
**Solution:** Add delays between requests:
```python
import time
for week in range(1, 18):
    data = espn.get_projections(week=week)
    time.sleep(1)  # 1 second delay
```

### Issue: Missing player stats
**Cause:** Player on bye or injured
**Solution:** Check player status before using:
```python
if row.get('injuryStatus') == 'ACTIVE':
    # Use player
```

## Advanced: Automated Lineup Setting

**⚠️ WARNING:** ESPN does not officially support automated lineup changes. Use at your own risk.

```python
# CONCEPTUAL ONLY - Requires additional auth
def set_lineup(espn, team_id, lineup_changes):
    """
    Set lineup for your team (advanced, not officially supported).

    This would require:
    1. POST requests to ESPN API
    2. CSRF tokens
    3. Session management
    4. Risk of account issues

    NOT RECOMMENDED for production use.
    """
    pass  # Not implementing for safety reasons
```

**Better Approach:** Use FFPy to **recommend** optimal lineups, then manually set them in ESPN.

## Integration with FFPy Streamlit UI

Add ESPN league data to the player comparison page:

```python
# In player_comparison.py
with st.sidebar:
    st.subheader("ESPN League Integration")

    league_id = st.text_input("League ID", help="Your ESPN league ID")
    swid = st.text_input("SWID Cookie", type="password")
    espn_s2 = st.text_input("ESPN_S2 Cookie", type="password")

    if st.button("Load My Roster"):
        espn = ESPNLeagueIntegration(league_id, swid, espn_s2)
        roster = espn.get_team_roster(team_id=1, week=week)
        st.success(f"Loaded {len(roster)} players from your roster!")
```

## Best Practices

1. **Cache API Responses:** Don't fetch the same data repeatedly
   ```python
   @st.cache_data(ttl=3600)  # Cache for 1 hour
   def get_espn_roster(league_id, team_id, week):
       espn = ESPNLeagueIntegration(...)
       return espn.get_team_roster(team_id, week)
   ```

2. **Store Cookies Securely:** Use environment variables, not hardcoded values

3. **Handle Errors Gracefully:**
   ```python
   try:
       roster = espn.get_team_roster(team_id, week)
   except Exception as e:
       st.error(f"Failed to load roster: {e}")
       roster = []
   ```

4. **Respect Rate Limits:** Add delays between requests

5. **Keep Cookies Fresh:** Cookies expire; re-authenticate periodically

## Privacy & Security

- ✅ **DO:** Store cookies in `.env` (gitignored)
- ✅ **DO:** Use environment variables in production
- ❌ **DON'T:** Commit cookies to git
- ❌ **DON'T:** Share cookies publicly
- ❌ **DON'T:** Automate lineup changes (violates ESPN ToS)

## Next Steps

1. **Implement Enhanced Integration:** Create `ESPNLeagueIntegration` class
2. **Add to Streamlit:** UI for ESPN league connection
3. **Build Roster Sync:** Auto-import your roster for optimization
4. **League Analyzer:** Compare all teams in your league

Would you like me to implement the enhanced ESPN integration with league roster access?
