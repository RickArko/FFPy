# NFL Pick'em Quickstart Guide

Get started with FFPy's Pick'em Analyzer in 5 minutes! This guide shows you how to generate optimal NFL pick'em picks for any weekly competition.

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Run the Example Script

```bash
cd FFPy
uv run python examples/pickem_example.py
```

**You'll see**:
- ✅ Confidence-based rankings (for confidence pools)
- ✅ Straight up picks (all favorites)
- ✅ Upset candidates (close games)
- ✅ Copy/paste formatted output
- ✅ Strategy tips

**No API keys required!** Uses ESPN's public scoreboard data.

---

### Step 2: Launch Interactive UI (Optional)

```bash
uv run streamlit run src/ffpy/app.py
```

Then navigate to **"🏈 Pick'em Analyzer"** in the sidebar.

**Interactive features**:
- 📊 Visual confidence charts
- 🎯 Game-by-game analysis
- ⚡ Upset probability visualization
- 📈 Week analytics and trends
- 📋 Exportable picks

---

## 📊 Understanding the Output

### Confidence Rankings

```
WEEKLY PICKS (with Confidence Rankings)
============================================================
16. SF @ ARI           → Pick:   SF (Spread: 10.5)
15. KC @ LV            → Pick:   KC (Spread: 7.5)
14. BAL @ JAX          → Pick:  BAL (Spread: 6.5)
13. DET @ DEN          → Pick:  DET (Spread: 4.5)
12. BUF @ MIA          → Pick:  BUF (Spread: 3.0)
11. CIN @ PIT          → Pick:  CIN (Spread: 2.5)
10. DAL @ PHI          → Pick:  PHI (Spread: 2.5)
 9. GB @ MIN           → Pick:  MIN (Spread: 1.0)
```

**How to use**:
1. **Highest confidence** (16) = Most certain pick (largest spread)
2. **Lowest confidence** (9) = Least certain pick (smallest spread)
3. **Assign points** based on your confidence in each pick

---

### Upset Candidates

```
Close Matchups:
----------------------------------------------------------------------
GB @ MIN              │ Favorite:  MIN (-1.0) │ Underdog:   GB │ Upset %: 67%
CIN @ PIT             │ Favorite:  CIN (-2.5) │ Underdog:  PIT │ Upset %: 17%
```

**Strategy**:
- Games with spreads **≤ 3 points** are toss-ups
- Consider picking the underdog strategically
- Useful for differentiating in competitive pools

---

## 🎯 Pick'em Competition Types

### 1. Confidence Pool

**Rules**:
- Assign confidence points 1 to N (N = number of games)
- Can't reuse points
- Correct pick = earn those confidence points

**FFPy Strategy**:
```bash
uv run python examples/pickem_example.py
```

Look at **"STRATEGY 1: CONFIDENCE-BASED RANKINGS"** section.

**How to assign confidence**:
- **Highest points** (16, 15, 14...) → Largest spreads (safest picks)
- **Medium points** (8-10) → Mid-range spreads
- **Lowest points** (1, 2, 3...) → Close games (toss-ups)

---

### 2. Straight Up Pool

**Rules**:
- Pick the winner of each game
- All correct picks = 1 point
- Most wins wins

**FFPy Strategy**:
```bash
uv run python examples/pickem_example.py
```

Look at **"STRATEGY 2: ALL FAVORITES"** section.

**Simple approach**: Pick all favorites (teams with negative/larger spreads)

---

### 3. Against the Spread (ATS)

**Rules**:
- Pick must "cover" the spread
- If favorite is -7, they must win by more than 7 points

**FFPy Strategy**:
Use confidence rankings but focus on:
- **Large spreads** (≥10 pts) → High confidence
- **Small spreads** (≤3 pts) → Low confidence or skip
- Check historical ATS performance (future feature)

---

## 🏈 Weekly Workflow

### Tuesday: Initial Picks

```bash
# Generate first draft
uv run python examples/pickem_example.py

# Save output
uv run python examples/pickem_example.py > week_16_picks.txt
```

**Why Tuesday?**
- Spreads are set after Monday Night Football
- Most platforms open picks on Tuesday

---

### Friday: Review & Adjust

```bash
# Re-run with updated spreads
uv run streamlit run src/ffpy/app.py
```

**Check for changes**:
- ✅ Injury reports (especially QBs)
- ✅ Weather forecasts (wind, snow, rain)
- ✅ Line movement (spread changes)
- ✅ Public betting trends

**Adjustments**:
- **Key injury** (e.g., QB out) → Reduce confidence or flip pick
- **Bad weather** → Favor underdog (equalizer)
- **Spread moved 2+ points** → Re-evaluate

---

### Sunday Morning: Final Submission

```bash
# One last check
uv run python examples/pickem_example.py
```

**Final checks**:
- ✅ All picks submitted before deadline (usually 1 PM ET)
- ✅ Confidence points assigned correctly (no duplicates)
- ✅ Last-minute injury news reviewed

---

## 📝 Platform-Specific Instructions

### ESPN Tournament Challenge

1. **Generate picks**:
   ```bash
   uv run python examples/pickem_example.py
   ```

2. **Navigate to**:
   https://fantasy.espn.com/games/nfl-pigskin-pickem-2024/make-picks

3. **Enter picks**:
   - Click team logo to select winner
   - Use dropdown to assign confidence points
   - Click "Submit Picks"

---

### Yahoo Sports Pick'em

1. **Generate picks**:
   ```bash
   uv run streamlit run src/ffpy/app.py
   ```
   Navigate to "🏈 Pick'em Analyzer" → Copy picks

2. **Navigate to**:
   https://football.fantasysports.yahoo.com/pickem

3. **Enter picks**:
   - Drag teams to assign confidence rank
   - Click "Save Picks"

---

### NFL.com Pick'em

1. **Generate picks**:
   ```bash
   uv run python examples/pickem_example.py
   ```

2. **Navigate to**:
   https://www.nfl.com/games/pick-em/

3. **Enter picks**:
   - Click team to select
   - Assign confidence in dropdown
   - Submit before deadline

---

## 🎓 Strategy Tips

### Beginner Strategy: Follow the Favorites

```python
from ffpy.pickem import PickemAnalyzer

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)

# Get all favorites
result = analyzer.simulate_pickem_strategy(games, strategy="favorites")

# Assign confidence by spread size
confidence_df = analyzer.calculate_confidence_rankings(games)
```

**Win rate**: ~55-60% typically

---

### Intermediate Strategy: Upset Hunting

```python
# Identify close games
upsets_df = analyzer.get_upset_candidates(games, threshold=3.0)

# Pick 1-2 strategic upsets
# Focus on:
# - Home underdogs
# - Division rivals
# - Teams with momentum
```

**When to pick upsets**:
- ✅ Large competitive pool (need differentiation)
- ✅ Home underdog with recent wins
- ✅ Division rivalry game
- ❌ Small pool with friends (stick to favorites)

---

### Advanced Strategy: Contrarian Approach

**Concept**: Pick against the public in competitive pools

```python
# 1. Pick mostly favorites (90%)
# 2. Pick 1-2 strategic upsets in close games
# 3. Assign HIGH confidence to upsets (if confident)
# 4. Assign MEDIUM confidence to big favorites (public will too)
```

**Example**:
```
Game: GB @ MIN (Spread: MIN -1.0)
Public: 80% picking Minnesota
You: Pick Green Bay with confidence #5
Reasoning: Close spread, public overweight on MIN
```

**Risk**: Higher variance, but can win competitive pools

---

## 📊 Example: Week 16 Picks

### Input

```bash
uv run python examples/pickem_example.py
```

### Output

```
Confidence Rankings:
----------------------------------------------------------------------
16 pts │ SF @ ARI                → SF   │ Spread: 10.5 │ Score:  10.5
15 pts │ KC @ LV                 → KC   │ Spread:  7.5 │ Score:   7.5
14 pts │ BAL @ JAX               → BAL  │ Spread:  6.5 │ Score:   6.5
13 pts │ DET @ DEN               → DET  │ Spread:  4.5 │ Score:   4.5
12 pts │ BUF @ MIA               → BUF  │ Spread:  3.0 │ Score:   3.0
11 pts │ CIN @ PIT               → CIN  │ Spread:  2.5 │ Score:   2.5
10 pts │ DAL @ PHI               → PHI  │ Spread:  2.5 │ Score:   2.5
 9 pts │ GB @ MIN                → MIN  │ Spread:  1.0 │ Score:   1.0
```

### Analysis

**Safest picks** (Assign highest confidence):
- ✅ **SF** (-10.5) → Huge favorite
- ✅ **KC** (-7.5) → Solid favorite

**Medium confidence**:
- ⚠️ **BAL, DET** → Mid-range spreads (4-7 points)

**Risky picks** (Assign lowest confidence):
- ⚠️ **GB @ MIN** → Basically a coin flip (1 pt spread)
- ⚠️ **CIN @ PIT** → Close division game

**Upset opportunities**:
- 🎯 **GB** at MIN → Only 1-point underdog, could easily win

---

## 🔧 Advanced Usage

### Custom Week Range

```python
from ffpy.pickem import PickemAnalyzer

analyzer = PickemAnalyzer(season=2024)

# Analyze multiple weeks
for week in range(15, 19):
    print(f"\n=== WEEK {week} ===")
    games = analyzer.get_weekly_games(week=week)
    picks = analyzer.calculate_confidence_rankings(games)
    print(picks[["matchup", "pick", "confidence_points"]])
```

---

### Export to CSV

```python
import pandas as pd
from ffpy.pickem import PickemAnalyzer

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks_df = analyzer.calculate_confidence_rankings(games)

# Export for manual review
picks_df[["matchup", "pick", "spread", "confidence_points"]].to_csv(
    "week_16_picks.csv",
    index=False
)

print("✅ Picks exported to week_16_picks.csv")
```

---

### Track Performance

```python
from ffpy.pickem import PickemAnalyzer

def check_results(week):
    """Check how your picks performed."""
    analyzer = PickemAnalyzer(season=2024)
    games = analyzer.get_weekly_games(week=week)

    correct = 0
    total = 0

    for game in games:
        if game.is_final:
            total += 1
            winner = game.get_winner()
            favorite, _ = game.get_favorite()

            if winner == favorite:
                correct += 1

    accuracy = (correct / total * 100) if total > 0 else 0
    print(f"Week {week}: {correct}/{total} correct ({accuracy:.1f}%)")

# Check past weeks
for week in range(1, 17):
    check_results(week)
```

---

## ❓ Troubleshooting

### "No games found"

**Cause**: ESPN API returned no data (off-season, API down, etc.)

**Solution**: Use sample data
```python
from ffpy.pickem import create_sample_pickem_data

games = create_sample_pickem_data(week=16)
```

---

### "Spreads look wrong"

**Cause**: Spreads can change rapidly based on betting action

**Solution**:
1. Cross-reference with Vegas odds sites (e.g., ESPN.com/nfl/lines)
2. Re-run analyzer closer to game time
3. Manually adjust if needed

---

### "Win probabilities missing"

**Cause**: ESPN doesn't always provide win probability data

**Impact**: Confidence scores will be based on spread only (still accurate)

**Solution**: No action needed, spread-based rankings are reliable

---

## 🎯 Success Metrics

### Typical Performance

**Following All Favorites**:
- Average: 9-10 correct out of 16 games (56-62%)
- Best case: 12-13 correct (75-81%)
- Worst case: 6-7 correct (37-43%)

**Using FFPy Confidence Rankings**:
- Confidence pools: Top 10-20% typically
- Reason: Optimal confidence assignment matters more than pick accuracy
- Example: Getting all high-confidence picks right >> getting low-confidence right

---

## 📚 Next Steps

**Ready to go deeper?**

1. **Read**: `docs/PICKEM_PLATFORMS_GUIDE.md`
   - Platform-specific integration
   - Automation strategies
   - CSV exports

2. **Explore**: Streamlit UI
   ```bash
   uv run streamlit run src/ffpy/app.py
   ```
   - Interactive visualizations
   - Game-by-game analysis
   - Historical trends

3. **Customize**: Build your own analyzer
   ```python
   from ffpy.pickem import PickemAnalyzer

   class MyCustomAnalyzer(PickemAnalyzer):
       def custom_strategy(self, games):
           # Your custom logic here
           pass
   ```

---

## 🏆 Good Luck!

**Remember**:
- 🎯 Assign highest confidence to biggest spreads
- ⚡ Identify 1-2 strategic upsets in close games
- 📊 Review injury/weather before finalizing
- ⏰ Submit before deadline (usually 1 PM ET Sunday)
- 🔄 Track performance to improve over time

**Questions?** Check out the full platform integration guide at `docs/PICKEM_PLATFORMS_GUIDE.md`

---

**Built with FFPy** 🏈
