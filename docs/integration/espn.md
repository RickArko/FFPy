# ESPN Fantasy Football Integration

## Quick Start

Get general ESPN projections with no auth:

```python
from ffpy.integrations.espn import ESPNIntegration
espn = ESPNIntegration()
projections = espn.get_projections(week=15, season=2024)
actuals = espn.get_actual_stats(week=14, season=2024)
```

For private league access (rosters, lineups, standings):

1. Find your League ID from the URL: `https://fantasy.espn.com/football/league?leagueId=123456`
2. For **private** leagues, get cookies via browser DevTools (F12 → Application → Cookies → `https://www.espn.com`): copy `swid` and `espn_s2`
3. Add to `.env`:
   ```bash
   ESPN_LEAGUE_ID=123456
   ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
   ESPN_S2=AEBxyz...long_string_here...xyz
   ```
4. Test: `uv run python examples/espn_league_example.py`

## What's Implemented

- `ESPNIntegration` (`src/ffpy/integrations/espn.py`) — public projections and actual stats, no auth
- `ESPNLeagueIntegration` (`src/ffpy/integrations/espn_league.py`) — private league data

## Usage

### View Your Roster

```python
from ffpy.integrations.espn_league import ESPNLeagueIntegration
espn = ESPNLeagueIntegration(league_id=123456)
roster = espn.get_team_roster(team_id=1, week=15)
print(roster[['player', 'position', 'lineup_slot', 'injury_status']])
```

### League Standings

```python
standings = espn.get_standings()
```

### Optimize From Your Roster

```python
from ffpy.integrations.espn import ESPNIntegration
from ffpy.integrations.espn_league import ESPNLeagueIntegration
from ffpy.optimizer import LineupOptimizer, RosterConstraints, Player

espn_league = ESPNLeagueIntegration(league_id=123456)
roster = espn_league.get_team_roster(team_id=1, week=15)
projections = ESPNIntegration().get_projections(week=15)
my_players = projections[projections['player'].isin(roster['player'])]
players = [Player(r['player'], r['position'], r['team'], r['projected_points'])
           for _, r in my_players.iterrows()]
result = LineupOptimizer(RosterConstraints.standard()).optimize(players)
print(f"Optimal: {result.total_points:.1f} pts")
```

### Compare All Teams

```python
rosters = espn.get_league_rosters(week=15)
for team_id, roster in rosters.items():
    team_players = projections[projections['player'].isin(roster['player'])]
    # optimize each team...
```

### Available Methods

| Method | Description |
|--------|-------------|
| `ESPNIntegration().get_projections(week, season)` | All player projections |
| `ESPNIntegration().get_actual_stats(week, season)` | Actual performance |
| `ESPNLeagueIntegration(league_id).get_team_roster(team_id, week)` | One team's roster |
| `ESPNLeagueIntegration().get_league_rosters(week)` | All rosters |
| `ESPNLeagueIntegration().get_standings()` | Current standings |
| `ESPNLeagueIntegration().get_matchups(week)` | Week's matchups |
| `ESPNLeagueIntegration().get_scoring_settings()` | League scoring rules |
| `ESPNLeagueIntegration().get_all_teams()` | Team info with records |
| `ESPNLeagueIntegration().get_league_info()` | Name, size, settings |

### Common Workflows

**Weekly lineup check:** `uv run python examples/espn_league_example.py`

**Trade evaluation:** compare player projections side-by-side using `get_projections()`.

**Waiver priority:** get free agents not on your roster, sort by projected_points.

## ESPN API Reference

### Public Endpoints

```
GET https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leaguedefaults/3
Params: scoringPeriodId={week}, view=kona_player_info
```

### Private Endpoints (requires cookies)

```
GET https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{leagueId}
Params: view=mRoster | mTeam | mSettings | mMatchup | mStandings
Headers: Cookie: swid={swid}; espn_s2={espn_s2}
```

### Data Structures

Lineup slot IDs: `0=QB, 2=RB, 4=WR, 6=TE, 16=D/ST, 17=K, 20=BENCH, 21=IR, 23=FLEX`

ScoringPeriodId maps to NFL weeks (1-18 regular season, 19+ playoffs).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 401 Unauthorized | Refresh cookies (they expire periodically) |
| Team not found | Run `espn.get_all_teams()` to verify team ID |
| Empty projections | ESPN API may be down; use `HistoricalProjectionModel` instead |
| Player name mismatch | ESPN uses full names; use fuzzy matching |

## Security

- Store cookies in `.env` (already in `.gitignore`)
- Never share `swid` or `espn_s2` publicly
- Automated lineup changes violate ESPN ToS — use FFPy for analysis only
- Cookies expire; re-authenticate periodically
