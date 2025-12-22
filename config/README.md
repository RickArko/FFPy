# FFPy Configuration Files

This directory contains configuration files for lineup optimization.

## Scoring Configurations

Located in `config/scoring/`, these define how player stats are converted to fantasy points.

### Available Presets

- **ppr.json**: Full Point Per Reception (1 point per catch)
- **half_ppr.json**: Half Point Per Reception (0.5 points per catch)
- **standard.json**: Standard scoring (no points for receptions)

### Usage

```python
from ffpy.scoring import ScoringConfig

# Load from file
config = ScoringConfig.from_json_file("config/scoring/ppr.json")

# Or use built-in presets
config = ScoringConfig.ppr()
config = ScoringConfig.half_ppr()
config = ScoringConfig.standard()
```

### Custom Scoring

You can create custom scoring configurations by:

1. Copying an existing JSON file
2. Modifying the values
3. Loading it with `ScoringConfig.from_json_file()`

Example custom configuration:
```json
{
  "name": "My League",
  "passing_yards_per_point": 20.0,
  "passing_td_points": 6.0,
  "reception_points": 1.0
}
```

## Roster Constraints

Located in `config/roster/`, these define lineup requirements and position limits.

### Available Presets

- **standard.json**: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DST
- **superflex.json**: 1 QB, 2 RB, 2 WR, 1 TE, 1 SUPERFLEX (can be QB), 1 K, 1 DST
- **no_kicker_dst.json**: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (skill positions only)

### Usage

```python
from ffpy.optimizer import RosterConstraints

# Load from file
constraints = RosterConstraints.from_json_file("config/roster/standard.json")

# Or use built-in presets
constraints = RosterConstraints.standard()
constraints = RosterConstraints.superflex()
constraints = RosterConstraints.no_kicker_dst()
```

### Custom Roster Constraints

You can create custom roster requirements:

```python
constraints = RosterConstraints(
    positions={"QB": 2, "RB": 2, "WR": 3, "TE": 1},
    flex_positions=["RB", "WR", "TE"],
    num_flex=2,
    max_players_per_team=3  # Stack limits
)
```

### Locking Players

Force specific players to start or sit:

```python
constraints = RosterConstraints.standard()
constraints.locked_in = {"Patrick Mahomes", "Travis Kelce"}  # Must start
constraints.locked_out = {"Injured Player"}  # Must bench
```

## Scoring Parameters Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `passing_yards_per_point` | 25.0 | Yards needed for 1 point |
| `passing_td_points` | 4.0 | Points per passing TD |
| `interception_points` | -2.0 | Penalty per INT |
| `rushing_yards_per_point` | 10.0 | Yards needed for 1 point |
| `rushing_td_points` | 6.0 | Points per rushing TD |
| `receiving_yards_per_point` | 10.0 | Yards needed for 1 point |
| `receiving_td_points` | 6.0 | Points per receiving TD |
| `reception_points` | 0.0 | Points per reception (PPR) |
| `fumble_lost_points` | -2.0 | Penalty per fumble lost |

## Roster Parameters Reference

| Parameter | Type | Description |
|-----------|------|-------------|
| `positions` | Dict[str, int] | Required starters per position |
| `flex_positions` | List[str] | Positions eligible for FLEX |
| `num_flex` | int | Number of FLEX spots |
| `max_players_per_team` | Optional[int] | Max players from same team |
| `locked_in` | List[str] | Players to force start |
| `locked_out` | List[str] | Players to force bench |
