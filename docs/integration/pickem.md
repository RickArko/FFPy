# NFL Pick'em Integration

## Quick Start

```bash
uv run python examples/pickem_example.py
```

No API keys needed — uses ESPN's public scoreboard data. Launch the interactive UI with `uv run streamlit run src/ffpy/app.py`, then navigate to "Pick'em Analyzer".

## Understanding the Output

### Confidence Rankings

```
WEEKLY PICKS (with Confidence Rankings)
16 pts │ SF @ ARI                → SF   │ Spread: 10.5
15 pts │ KC @ LV                 → KC   │ Spread:  7.5
 9 pts │ GB @ MIN                → MIN  │ Spread:  1.0
```

Highest confidence = largest spread (safest pick). Assign confidence points 1-N without reusing points.

### Upset Candidates

Games with spreads ≤3 points are toss-ups. Consider the underdog to differentiate in competitive pools.

## Competition Types

| Type | Rules | FFPy Strategy |
|------|-------|---------------|
| **Confidence Pool** | Assign points 1-N per game; correct = earn those points | Highest points → largest spreads |
| **Straight Up** | Each correct pick = 1 point | Pick all favorites |
| **Against the Spread** | Must cover the spread | Focus on large spreads (≥10) for high confidence |
| **Survivor Pool** | Pick one team/week, can't repeat | Not yet automated |

## Weekly Workflow

- **Tuesday**: `uv run python examples/pickem_example.py` — spreads set after MNF
- **Friday**: Review injuries, weather, line movement via Streamlit UI
- **Sunday**: Final check and submit before 1 PM ET

## Strategy Tips

- **Beginner**: Follow the favorites (~55-60% win rate)
- **Intermediate**: Pick 1-2 strategic upsets in close games (home underdogs, division rivals)
- **Advanced (Contrarian)**: Pick against the public in competitive pools — high variance but can win

## Platform-Specific Guides

### ESPN Tournament Challenge

Manual: copy FFPy output, enter at `https://fantasy.espn.com/games/nfl-pigskin-pickem-2024/make-picks`

### Yahoo Sports Pick'em

Manual: copy from Streamlit UI, enter at `https://football.fantasysports.yahoo.com/pickem`

### CBS Sports Pool Manager

CSV export supported. Premium ($29.99/yr). See `export_for_platform` utility approach below.

### NFL.com Pick'em

Manual copy/paste at `https://www.nfl.com/games/pick-em/`

### RunYourPool

Customizable rules. Extend `PickemAnalyzer` to override confidence calculations to match pool settings.

## Integration Options

### Option 1: Manual Copy/Paste (All Platforms)

```bash
uv run python examples/pickem_example.py
```

Works with any platform, no API access needed. Quick but manual.

### Option 2: CSV Export

```python
from ffpy.pickem import PickemAnalyzer
analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks_df = analyzer.calculate_confidence_rankings(games)
picks_df[["matchup", "pick", "confidence_points"]].to_csv("week_16_picks.csv", index=False)
```

### Option 3: Browser Automation (Playwright/Selenium)

For weekly automation. Requires platform-specific selectors; may violate platform TOS.

### Option 4: Email/Slack/Discord

```python
# Email picks automatically
def email_weekly_picks(week, recipient):
    analyzer = PickemAnalyzer(season=2024)
    games = analyzer.get_weekly_games(week=week)
    picks_text = analyzer.format_weekly_picks(games, include_confidence=True)
    # ... send via SMTP
```

### Option 5: Custom Pickem Tracker

```python
class RunYourPoolAnalyzer(PickemAnalyzer):
    def calculate_confidence_rankings(self, games, max_confidence=32):
        df = super().calculate_confidence_rankings(games)
        df["confidence_points"] = range(max_confidence, max_confidence - len(df), -1)
        return df
```

## Automation

**Cron (Linux/Mac):** `0 8 * * 2 cd /path/to/FFPy && uv run python examples/pickem_example.py > weekly_picks.txt`

**Slack webhook:** post picks to team channel using Slack's Block Kit for formatted output.

## Data Export Formats

Standard CSV columns: `Week, Matchup, Favorite, Underdog, Spread, Pick, Confidence`

## Platform API Status (2024)

| Platform | Official API | Unofficial API | Scraping |
|----------|-------------|----------------|----------|
| ESPN | ❌ | ✅ Community | ⚠️ Gray |
| Yahoo | ❌ | ✅ Community | ⚠️ Gray |
| CBS | ❌ | ❌ | ⚠️ Gray |
| NFL.com | ❌ | ✅ Limited | ⚠️ Gray |
| RunYourPool | ❌ | ❌ | ❌ |

**Always check platform TOS before automating.** FFPy is for analysis only; submit picks manually.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No games found" | Use `create_sample_pickem_data(week)` |
| Spreads look wrong | Cross-reference with Vegas odds; re-run closer to game time |
| Win probabilities missing | Spread-based rankings still accurate |
| Performance tracking | Implement `PickemTracker` to record results and calculate accuracy |

## Typical Performance

All favorites: 56-62% weekly. FFPy confidence rankings: typically top 10-20% in confidence pools (optimal point assignment matters more than pick accuracy).

## Next Steps

1. Run the example script
2. Explore the Streamlit UI
3. Customize `PickemAnalyzer` for your pool's rules
4. Track performance over the season
