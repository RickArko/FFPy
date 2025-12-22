# NFL Pick'em Platforms Integration Guide

This guide covers popular NFL pick'em competition platforms and how to integrate FFPy's Pick'em Analyzer with them.

---

## 📋 Table of Contents

1. [Platform Comparison](#platform-comparison)
2. [Integration Options](#integration-options)
3. [Platform-Specific Guides](#platform-specific-guides)
4. [Data Export Formats](#data-export-formats)
5. [Automation Strategies](#automation-strategies)

---

## Platform Comparison

### Overview of Popular Pick'em Platforms

| Platform | Type | Confidence Points | API Access | Cost | Best For |
|----------|------|------------------|------------|------|----------|
| **ESPN Tournament Challenge** | Straight/Confidence | ✅ Yes | ❌ No | Free | Casual groups, large pools |
| **Yahoo Sports Pick'em** | Straight/Confidence | ✅ Yes | ❌ No | Free | Friends & family pools |
| **CBS Sports Pool Manager** | Confidence | ✅ Yes | ❌ No | Premium ($30/yr) | Serious pools, advanced stats |
| **NFL.com Pick'em** | Straight/Confidence | ✅ Yes | ❌ No | Free | Official NFL integration |
| **RunYourPool** | Confidence/Survivor | ✅ Yes | ❌ No | Premium ($30-80/yr) | Custom rules, large leagues |
| **OfficePools** | Confidence | ✅ Yes | ❌ No | Premium ($20-60/yr) | Office pools, playoffs |
| **Fox Sports Super 6** | Straight | ❌ No | ❌ No | Free | Casual, prizes |
| **Pickem.com** | Confidence/Straight | ✅ Yes | ❌ No | Premium ($20/yr) | Simple interface |

### Pick'em Format Types

**1. Straight Up Pick'em**
- Pick the winner of each game (no point spreads)
- Each correct pick = 1 point
- Most total points wins
- **Platforms**: ESPN, Yahoo, NFL.com, Fox Super 6

**2. Confidence Pool**
- Assign confidence points to each pick (1 to N games)
- Each correct pick earns its assigned confidence points
- Cannot reuse confidence points
- **Platforms**: ESPN, Yahoo, CBS, NFL.com, RunYourPool

**3. Against the Spread (ATS)**
- Pick winners using Vegas point spreads
- Must cover the spread to win
- **Platforms**: CBS Sports, RunYourPool (custom)

**4. Survivor Pool**
- Pick one team to win each week
- Can only pick each team once per season
- One loss = elimination
- **Platforms**: RunYourPool, OfficePools, Survivor Grid

---

## Integration Options

### Option 1: Manual Copy/Paste (All Platforms)

**Best for**: Any platform, quick weekly picks

**How it works**:
1. Run FFPy Pick'em Analyzer to generate picks
2. Copy formatted output
3. Manually enter picks on platform website

**Steps**:

```bash
# Run analyzer
uv run python examples/pickem_example.py

# Or use Streamlit UI
uv run streamlit run src/ffpy/app.py
```

**Pros**:
- ✅ Works with any platform
- ✅ No API access needed
- ✅ Quick and simple

**Cons**:
- ❌ Manual data entry
- ❌ Not automated
- ❌ Prone to typos

---

### Option 2: Browser Automation (ESPN, Yahoo, NFL.com)

**Best for**: Weekly automation, competitive pools

**How it works**:
1. Use Selenium/Playwright to automate browser
2. Log into platform automatically
3. Fill in picks from FFPy output
4. Submit picks

**Example using Playwright**:

```python
from playwright.sync_api import sync_playwright
from ffpy.pickem import PickemAnalyzer

def submit_espn_picks(username, password, week, picks):
    """Submit picks to ESPN Tournament Challenge."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Login to ESPN
        page.goto("https://www.espn.com/login")
        page.fill('input[placeholder="Username or Email"]', username)
        page.fill('input[placeholder="Password"]', password)
        page.click('button[type="submit"]')

        # Navigate to pick'em
        page.goto(f"https://fantasy.espn.com/games/nfl-pigskin-pickem-2024/make-picks?week={week}")

        # Fill in picks
        for pick in picks:
            # Find game element and click team
            selector = f'[data-game-id="{pick["game_id"]}"] [data-team="{pick["team"]}"]'
            page.click(selector)

            # Set confidence if applicable
            if "confidence" in pick:
                conf_selector = f'[data-game-id="{pick["game_id"]}"] select'
                page.select_option(conf_selector, str(pick["confidence"]))

        # Submit
        page.click('button[type="submit"]')

        browser.close()

# Usage
analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks_df = analyzer.calculate_confidence_rankings(games)

# Convert to format for automation
picks = []
for _, row in picks_df.iterrows():
    picks.append({
        "game_id": row["game"].game_id,
        "team": row["pick"],
        "confidence": row["confidence_points"]
    })

submit_espn_picks("your_username", "your_password", week=16, picks=picks)
```

**Pros**:
- ✅ Fully automated
- ✅ No manual data entry
- ✅ Can schedule weekly

**Cons**:
- ❌ Requires platform-specific selectors
- ❌ Breaks if platform updates UI
- ❌ Needs browser automation setup
- ❌ May violate platform TOS (check first!)

**Recommended Libraries**:
- **Playwright** (modern, reliable): `pip install playwright`
- **Selenium** (classic): `pip install selenium`

---

### Option 3: CSV/Excel Export (CBS Sports, RunYourPool)

**Best for**: Platforms that accept bulk uploads

**How it works**:
1. Generate picks with FFPy
2. Export to CSV/Excel format
3. Upload to platform

**Example**:

```python
from ffpy.pickem import PickemAnalyzer
import pandas as pd

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks_df = analyzer.calculate_confidence_rankings(games)

# Export to CSV
export_df = picks_df[["matchup", "pick", "confidence_points"]].copy()
export_df.columns = ["Game", "Team", "Confidence"]
export_df.to_csv("week_16_picks.csv", index=False)

print("✅ Picks exported to week_16_picks.csv")
```

**Pros**:
- ✅ Clean data format
- ✅ Easy to review
- ✅ Works with Excel

**Cons**:
- ❌ Platform must support uploads
- ❌ Still requires manual upload
- ❌ Format must match platform

---

### Option 4: API Integration (Future/Custom Platforms)

**Best for**: Custom pools, advanced users

**Status**: ⚠️ Most platforms don't offer public APIs

**Potential Custom Solution**:

```python
# Example: Custom pick'em tracker with database
from ffpy.pickem import PickemAnalyzer
from ffpy.database import Database

class CustomPickemTracker:
    """Track picks across multiple platforms."""

    def __init__(self):
        self.db = Database()
        self.analyzer = PickemAnalyzer()

    def generate_weekly_picks(self, week):
        """Generate and store picks."""
        games = self.analyzer.get_weekly_games(week)
        picks_df = self.analyzer.calculate_confidence_rankings(games)

        # Store in database
        for _, row in picks_df.iterrows():
            self.db.execute("""
                INSERT INTO weekly_picks (week, game_id, team, confidence)
                VALUES (?, ?, ?, ?)
            """, (week, row["game"].game_id, row["pick"], row["confidence_points"]))

        return picks_df

    def export_for_platform(self, platform, week):
        """Export picks in platform-specific format."""
        if platform == "espn":
            return self._export_espn_format(week)
        elif platform == "yahoo":
            return self._export_yahoo_format(week)
        # ... more platforms
```

---

## Platform-Specific Guides

### 🏈 ESPN Tournament Challenge

**Website**: https://fantasy.espn.com/games/nfl-pigskin-pickem-2024

**Features**:
- Free to play
- Straight up OR confidence pools
- Create private groups
- Mobile app available

**Integration Approach**:
1. **Manual**: Copy picks from FFPy Streamlit UI
2. **Semi-Automated**: Use FFPy CLI output and manually enter

**Pick Submission**:
1. Navigate to "Make Picks" page
2. Click team logos to select winners
3. For confidence pools, assign points via dropdowns
4. Click "Submit Picks" before deadline

**FFPy Workflow**:

```bash
# Generate picks
uv run python examples/pickem_example.py

# Or use Streamlit
uv run streamlit run src/ffpy/app.py
# Navigate to "🏈 Pick'em Analyzer" page
# Export formatted picks and copy/paste to ESPN
```

---

### 🏈 Yahoo Sports Pick'em

**Website**: https://football.fantasysports.yahoo.com/pickem

**Features**:
- Free
- Confidence and straight pools
- Tracks historical performance
- Integration with Yahoo Fantasy Football

**Integration Approach**:
1. **Manual**: Copy from FFPy output
2. **Automation**: Playwright/Selenium (see Option 2)

**Pick Format**:
- Confidence: Drag and drop teams to assign confidence ranks
- Straight: Click team to select winner

**FFPy Export**:

```python
from ffpy.pickem import PickemAnalyzer

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)

# Generate formatted output for Yahoo
formatted = analyzer.format_weekly_picks(games, include_confidence=True)
print(formatted)
```

---

### 🏈 CBS Sports Pool Manager

**Website**: https://www.cbssports.com/nfl/office-pool/

**Features**:
- Premium ($29.99/year)
- Confidence pools
- Advanced stats and analytics
- Commissioner tools

**Integration Approach**:
1. **CSV Upload**: Export FFPy picks to CSV (if supported)
2. **Manual**: Use FFPy confidence rankings

**Data Export Example**:

```python
from ffpy.pickem import PickemAnalyzer
import pandas as pd

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks = analyzer.calculate_confidence_rankings(games)

# Format for CBS
cbs_export = []
for _, row in picks.iterrows():
    away, home = row["matchup"].split(" @ ")
    cbs_export.append({
        "Away Team": away,
        "Home Team": home,
        "Pick": row["pick"],
        "Confidence": int(row["confidence_points"])
    })

df = pd.DataFrame(cbs_export)
df.to_csv("cbs_picks_week16.csv", index=False)
```

---

### 🏈 NFL.com Pick'em

**Website**: https://www.nfl.com/games/pick-em/

**Features**:
- Official NFL platform
- Free
- Confidence and straight formats
- Real-time scoring

**Integration Approach**: Manual copy/paste

**Workflow**:
1. Run FFPy analyzer
2. Copy confidence rankings
3. Enter on NFL.com manually

---

### 🏈 RunYourPool

**Website**: https://www.runyourpool.com/

**Features**:
- Premium ($29-79/year)
- Highly customizable rules
- Survivor, confidence, ATS pools
- Best for large/competitive pools

**Integration Approach**:
1. **Custom Rules**: Configure FFPy to match pool settings
2. **Export**: Generate CSV exports
3. **Manual Entry**: Use formatted output

**Custom Configuration Example**:

```python
from ffpy.pickem import PickemAnalyzer

# Custom analyzer for RunYourPool settings
class RunYourPoolAnalyzer(PickemAnalyzer):
    def calculate_confidence_rankings(self, games, max_confidence=32):
        """Override to match pool settings."""
        df = super().calculate_confidence_rankings(games)

        # Adjust confidence to max (e.g., 32 for all games + playoffs)
        df["confidence_points"] = range(max_confidence, max_confidence - len(df), -1)

        return df

analyzer = RunYourPoolAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
picks = analyzer.calculate_confidence_rankings(games, max_confidence=32)
```

---

## Data Export Formats

### Standard CSV Format

```csv
Week,Matchup,Favorite,Underdog,Spread,Pick,Confidence
16,BUF @ LAC,BUF,LAC,3.5,BUF,16
16,KC @ PIT,KC,PIT,7.0,KC,15
16,SF @ MIA,SF,MIA,10.5,SF,14
```

### Confidence Points Only

```csv
Game,Team,Confidence
Buffalo @ LA Chargers,BUF,16
Kansas City @ Pittsburgh,KC,15
San Francisco @ Miami,SF,14
```

### Full Analysis Export

```python
from ffpy.pickem import PickemAnalyzer

analyzer = PickemAnalyzer(season=2024)
games = analyzer.get_weekly_games(week=16)
confidence_df = analyzer.calculate_confidence_rankings(games)

# Export comprehensive analysis
confidence_df.to_csv("week_16_full_analysis.csv", index=False)

# Export summary for platform submission
summary = confidence_df[["matchup", "pick", "confidence_points"]]
summary.to_csv("week_16_picks.csv", index=False)
```

---

## Automation Strategies

### Weekly Cron Job

**Setup**: Run FFPy analyzer automatically every Tuesday

**Linux/Mac (crontab)**:

```bash
# Edit crontab
crontab -e

# Add entry to run every Tuesday at 8 AM
0 8 * * 2 cd /path/to/FFPy && /path/to/uv run python examples/pickem_example.py > weekly_picks.txt
```

**Windows (Task Scheduler)**:
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Weekly (Tuesday, 8 AM)
4. Action: Run program
   - Program: `uv.exe`
   - Arguments: `run python examples/pickem_example.py`
   - Start in: `C:\path\to\FFPy`

---

### Email Picks Workflow

**Send picks via email automatically**:

```python
import smtplib
from email.mime.text import MIMEText
from ffpy.pickem import PickemAnalyzer

def email_weekly_picks(week, recipient_email):
    """Generate picks and email them."""

    # Generate picks
    analyzer = PickemAnalyzer(season=2024)
    games = analyzer.get_weekly_games(week=week)
    picks_text = analyzer.format_weekly_picks(games, include_confidence=True)

    # Create email
    msg = MIMEText(picks_text)
    msg["Subject"] = f"Week {week} NFL Pick'em Picks"
    msg["From"] = "your_email@gmail.com"
    msg["To"] = recipient_email

    # Send via Gmail SMTP
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("your_email@gmail.com", "your_app_password")
        server.send_message(msg)

    print(f"✅ Picks emailed to {recipient_email}")

# Run weekly
email_weekly_picks(week=16, recipient_email="you@example.com")
```

---

### Slack/Discord Integration

**Post picks to team channel**:

```python
import requests
from ffpy.pickem import PickemAnalyzer

def post_to_slack(webhook_url, week):
    """Post picks to Slack channel."""

    analyzer = PickemAnalyzer(season=2024)
    games = analyzer.get_weekly_games(week=week)
    picks_text = analyzer.format_weekly_picks(games, include_confidence=True)

    payload = {
        "text": f"🏈 *Week {week} Pick'em Picks*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```\n{picks_text}\n```"
                }
            }
        ]
    }

    response = requests.post(webhook_url, json=payload)
    return response.status_code == 200

# Usage
SLACK_WEBHOOK = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
post_to_slack(SLACK_WEBHOOK, week=16)
```

---

## Best Practices

### 1. Weekly Workflow

**Tuesday**: Games and spreads finalized
```bash
# Generate initial picks
uv run python examples/pickem_example.py
```

**Friday**: Review injury reports, weather
```bash
# Re-run with updated data
uv run streamlit run src/ffpy/app.py
# Manually adjust for injuries/weather
```

**Sunday Morning**: Final review and submit
```bash
# Last chance for adjustments
# Submit to platform before 1 PM ET kickoff
```

### 2. Track Performance

**Monitor accuracy over time**:

```python
from ffpy.database import Database
from ffpy.pickem import PickemAnalyzer

class PickemTracker:
    """Track pick accuracy over season."""

    def __init__(self):
        self.db = Database()
        self.analyzer = PickemAnalyzer()

    def record_weekly_results(self, week):
        """Store actual results."""
        games = self.analyzer.get_weekly_games(week)

        for game in games:
            if game.is_final:
                winner = game.get_winner()
                self.db.execute("""
                    UPDATE weekly_picks
                    SET actual_winner = ?, correct = (pick = ?)
                    WHERE week = ? AND game_id = ?
                """, (winner, winner, week, game.game_id))

    def get_season_accuracy(self):
        """Calculate overall accuracy."""
        results = self.db.query("""
            SELECT
                COUNT(*) as total_picks,
                SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct_picks,
                ROUND(AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0 END) * 100, 1) as accuracy
            FROM weekly_picks
            WHERE actual_winner IS NOT NULL
        """)

        return results[0]
```

### 3. Differentiation Strategy

**In competitive pools, strategic upsets can win**:

```python
def generate_contrarian_picks(games, upset_picks=2):
    """Pick strategic upsets to differentiate."""

    analyzer = PickemAnalyzer()

    # Get standard picks
    standard = analyzer.calculate_confidence_rankings(games)

    # Get upset candidates
    upsets = analyzer.get_upset_candidates(games, threshold=3.0)

    # Pick top N upsets with lowest confidence
    if len(upsets) >= upset_picks:
        # Swap picks for closest games
        for i in range(upset_picks):
            upset_game = upsets.iloc[i]
            # Find in standard picks and swap
            # Assign low confidence to upset picks
            pass

    return standard
```

---

## Platform API Status (as of 2024)

| Platform | Official API | Unofficial API | Scraping Allowed |
|----------|-------------|----------------|------------------|
| ESPN | ❌ No | ✅ Community | ⚠️ Gray Area |
| Yahoo | ❌ No | ✅ Community | ⚠️ Gray Area |
| CBS Sports | ❌ No | ❌ No | ⚠️ Gray Area |
| NFL.com | ❌ No | ✅ Limited | ⚠️ Gray Area |
| RunYourPool | ❌ No | ❌ No | ❌ No |

**⚠️ Important**: Always check platform Terms of Service before automating. Most platforms prohibit automated submissions.

**Recommended Approach**: Use FFPy for **analysis only**, submit picks manually.

---

## Summary

**Best Integration Methods by Use Case**:

| Use Case | Recommended Method | Platforms |
|----------|-------------------|-----------|
| Casual weekly picks | Manual copy/paste | All |
| Serious competitive pool | CSV export + manual review | CBS, RunYourPool |
| Office pool automation | Email/Slack bot | All |
| Multiple platforms | Custom tracker + exports | All |
| Learning/Analysis | Streamlit UI | All |

**Next Steps**:
1. Choose your platform
2. Set up FFPy Pick'em Analyzer
3. Run example script to test
4. Decide on integration method
5. Automate if desired (carefully!)

---

**Questions?** See `docs/PICKEM_QUICKSTART.md` for getting started guide.
