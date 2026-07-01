# FFPy Analysis Notebooks

This directory contains Jupyter notebooks for exploratory data analysis and advanced analytics.

## Setup

Install analysis dependencies (or just run `make notebook`):

```bash
uv sync --group analysis
```

This installs:
- Jupyter Notebook
- Matplotlib (plotting)
- Seaborn (statistical visualization)
- NumPy (numerical computing)

## Available Notebooks

### Optimization Notebook Series

A progression of notebooks exploring lineup optimisation concepts, from scoring
system fundamentals through to Monte Carlo robustness analysis.

**Prerequisite:** `make install` (FFPy dependencies). No database required —
all three notebooks construct in-memory player pools.

Recommended order:

1. **`01_scoring_systems_impact.ipynb` — Scoring & Valuation**
   - How PPR, Half-PPR, Standard, and custom scoring rules change player value
   - Positional value shifts (which positions gain/lose from reception points)
   - Optimising the same player pool under different scoring systems
   - Defining a "Big Play Bonus" custom rule

2. **`02_optimizer_constraints.ipynb` — Constraint Deep Dive**
   - Standard vs Superflex vs No-Kicker/DST roster formats
   - Player locks (forced starts/sits) — measuring the cost in projected points
   - Injury status handling (INJURED, OUT, QUESTIONABLE, BYE)
   - Team stack limits (max N players per NFL team)
   - Salary cap knapsack (DFS-style), sweeping cap vs efficiency
   - Combining multiple constraints for league-specific rules

3. **`03_projection_uncertainty.ipynb` — Robust Lineups**
   - Why a single "optimal" lineup is fragile — projections have variance
   - Monte Carlo simulation framework (1,000+ simulated outcome worlds)
   - Player selection frequency — who are the "core" starters?
   - Lineup score distribution (ceiling vs floor analysis)
   - Comparing point-maximising vs floor-maximising strategies
   - Sensitivity analysis: how projection changes ripple through the lineup

4. **`xpress_vs_pulp_ff_lineup.ipynb` (existing) — Solver Comparison**
   - PuLP/CBC vs FICO Xpress on three problem tiers (single, DFS, multi-lineup)
   - Model formulation side-by-side (API comparison table)
   - Benchmark: solve time vs problem size

5. **`04_draft_strategy_macker.ipynb` — Dynasty Draft Strategy (correlation-aware)**
   - Recommends three snake picks for a Sleeper dynasty league
   - Blends positional need, ADP value, preseason VORP, and weekly starter correlation
   - Uses imported league rosters + `ffpy-db load-adp`
   - Requires populated `actual_stats` (2023–2025) and imported league data

### `eda/Players.ipynb` - Player Performance Analysis

Comprehensive exploratory data analysis of the FFPy database:

**What it covers:**
- Database overview (player counts, positions)
- Available statistics at game level
- Data quality checks
- Fantasy points distribution by position
- Top performers analysis
- Week-by-week performance trends
- Individual player deep dives
- Position-specific stats breakdown
- Consistency analysis
- Data granularity summary

**Sections:**
1. Database Overview
2. Player Breakdown by Position
3. Available Statistics (Game-Level Data)
4. Statistical Categories
5. Player Lists by Position
6. Data Quality Check
7. Fantasy Points Distribution
8. Top Performers by Position
9. Week-by-Week Performance Trends
10. Individual Player Deep Dive
11. Position-Specific Stats Analysis
12. Consistency Analysis
13. Data Granularity Summary
14. Export Sample Data

## Running the Notebooks

### Option 1: Makefile (recommended)

```bash
make notebook
```

Equivalent to `uv run --group analysis jupyter lab`. Navigate to any notebook under
`notebooks/` in the browser.

### Option 2: Jupyter Notebook

```bash
uv run --group analysis jupyter notebook
```

### Option 3: VS Code

1. Install the Jupyter extension in VS Code
2. Open any notebook under `notebooks/`
3. Select the Python kernel from your uv environment

## Notebook Output

The notebook generates:
- **Visualizations**: Distribution plots, trend lines, scatter plots, bar charts
- **Summary tables**: Player statistics, position breakdowns, consistency metrics
- **CSV exports**: Located in `data/exports/` for external analysis

### Exported Files

Running the notebook creates:
- `data/exports/player_averages_2024.csv` - Season averages per player
- `data/exports/full_stats_2024.csv` - Complete week-by-week dataset

## Key Insights from Analysis

### Database Contents
- **680 total records** (40 players × 17 weeks)
- **40 unique players** across QB, RB, WR, TE positions
- **17 weeks** of 2024 season data (weeks 1-17)
- **100% data completeness** - no missing values

### Available Stats (Game Level)
- Passing: yards, touchdowns
- Rushing: yards, touchdowns
- Receiving: yards, touchdowns, receptions
- Fantasy points (PPR scoring)

### Granularity
- **Week-by-week** performance tracking
- **Sufficient for**: Historical projections, trend analysis, player comparisons
- **Not included**: Play-by-play, snap counts, target share, red zone stats

## Customizing the Analysis

### Analyze Specific Players

```python
# Add a cell to focus on specific players
player_name = "Josh Allen"
player_data = stats[stats['player'] == player_name]
player_data.plot(x='week', y='actual_points', kind='line')
```

### Compare Multiple Players

```python
import matplotlib.pyplot as plt

players = ["Josh Allen", "Patrick Mahomes", "Lamar Jackson"]
fig, ax = plt.subplots(figsize=(12, 6))

for player in players:
    player_data = stats[stats['player'] == player]
    ax.plot(player_data['week'], player_data['actual_points'], marker='o', label=player)

ax.legend()
ax.set_title("QB Comparison")
plt.show()
```

### Filter by Date Range

```python
# Analyze specific weeks
recent_weeks = stats[stats['week'] >= 10]
recent_avg = recent_weeks.groupby('player')['actual_points'].mean()
```

## Tips for Analysis

1. **Check data quality first**: Run cells 1-6 to understand what's available
2. **Focus by position**: QB, RB, WR, TE have different stat profiles
3. **Look for trends**: Week-over-week patterns reveal consistency
4. **Export for sharing**: Use CSV exports to share findings with your league

## Troubleshooting

### "Module not found" errors

Ensure analysis dependencies are installed:
```bash
uv sync --group analysis
```

### "Database not found" error

Make sure the database is populated:
```bash
make db.mock SEASON=2024        # realistic mock data
# or
make db.load SEASON=2024        # real nflverse play-by-play
```

### Kernel crashes

Try restarting the kernel: `Kernel → Restart & Clear Output`

## Next Steps

After running `Players.ipynb`, you might want to:
- Create custom notebooks for specific analyses
- Add notebooks for projection model evaluation
- Build notebooks comparing projections vs actuals
- Develop advanced ML model notebooks

## Contributing

To add a new notebook:
1. Create it in an appropriate subdirectory (e.g., `notebooks/modeling/`)
2. Document it in this README
3. Ensure it's reproducible with the existing database

---

## Regenerating Optimization Notebooks

The three optimisation notebooks (`01_*`, `02_*`, `03_*`) are generated from a single
Python script at `scripts/generate_optimization_notebooks.py`. To regenerate:

```bash
uv run python scripts/generate_optimization_notebooks.py
```

This is useful if you modify the generator to add new sections or change shared
sample data. The `xpress_vs_pulp_ff_lineup.ipynb` and `eda/*.ipynb` notebooks are
hand-written and not affected.

**Quick Start**: `make notebook`
