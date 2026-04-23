# Contributing to FFPy

**Welcome!** This guide is for students, data scientists, and anyone who wants to contribute - no advanced coding experience required.

## Getting Started

### 1. Set Up the Project

Follow [QUICKSTART.md](QUICKSTART.md) to get the app running on your machine.

**Summary:**
```bash
# First time: installs uv, deps, .env, DB schema
make bootstrap

# Run
make run
```

Run `make help` to see every target. Windows users: run from **WSL**.

### 2. Make Your Changes

Edit the code using any text editor:
- **Visual Studio Code** (recommended, free)
- **PyCharm** (popular for Python)
- **Notepad++** (simple, Windows)
- **Any editor** you're comfortable with

### 3. Test Your Changes

Run the app with auto-reload so your edits are picked up on save:

```bash
make dev
```

Run the test suite before opening a PR:

```bash
make check   # ruff + pytest
```

## Project Structure (Where to Edit)

```
FFPy/
├── src/ffpy/
│   ├── app.py              ← Main UI (Streamlit interface)
│   ├── data.py             ← Data fetching and caching
│   ├── config.py           ← Settings (API keys, etc.)
│   └── integrations/
│       ├── espn.py         ← ESPN API integration
│       └── sportsdata.py   ← SportsDataIO API integration
│
├── .env                     ← Your API configuration
├── QUICKSTART.md           ← Beginner guide
└── README.md               ← Main documentation
```

## Easy Contributions (No Coding!)

### 1. Improve Documentation
- Fix typos in README.md or QUICKSTART.md
- Add clearer instructions
- Add screenshots
- Translate to other languages

### 2. Test the App
- Try the app on different operating systems
- Report bugs you find
- Suggest UX improvements

### 3. Add Sample Data
- Add more realistic player projections in `data.py`
- Update team names or player names

## Code Contributions (Beginner-Friendly)

### 1. UI Improvements (Edit `app.py`)

**Example: Change the title**
```python
# Before (line 23)
st.title("🏈 Fantasy Football Point Projections")

# After
st.title("🏈 FF Projections - Week by Week")
```

**Example: Add a new metric**
```python
# In the metrics section (around line 58), add a new column
col5 = st.columns(5)  # Change from 4 to 5
with col5:
    st.metric("Total Points", f"{projections['projected_points'].sum():.0f}")
```

### 2. Add New Features (Small Changes)

**Example: Add a "Reset Filters" button**

In `app.py`, add this after the filters:
```python
if st.sidebar.button("Reset All Filters"):
    st.rerun()
```

**Example: Export data to CSV**

In `app.py`, add this near the table:
```python
csv = projections.to_csv(index=False)
st.download_button(
    label="Download as CSV",
    data=csv,
    file_name=f"projections_week_{week}.csv",
    mime="text/csv"
)
```

### 3. Add Styling (Edit `app.py`)

**Example: Add custom CSS**

```python
# Add this near the top of main()
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)
```

## Advanced Contributions

### 1. Add a New API Integration

See `src/ffpy/integrations/espn.py` as a template. Steps:

1. Create `src/ffpy/integrations/your_api.py`
2. Inherit from `BaseAPIIntegration`
3. Implement `get_projections()` method
4. Add config to `.env.example`
5. Update `data.py` to use your new integration

### 2. Add Database Support

Current setup uses APIs only. You could:
- Add SQLite for local storage
- Store historical projections
- Enable offline mode

### 3. Add Machine Learning

Build your own projections:
- Train models on historical data
- Predict player performance
- Compare ML projections vs API projections

## Testing Your Contribution

### Basic Testing

1. **Run the app:**
   ```bash
   make run
   ```

2. **Check all features still work:**
   - Toggle real-time data
   - Change weeks
   - Change positions
   - Check metrics update

3. **Run the automated suite:**
   ```bash
   make check
   ```

### Advanced Testing

See [TESTING.md](TESTING.md) for comprehensive test scenarios.

## Submitting Your Contribution

### If Using Git (Recommended)

```bash
# 1. Create a new branch
git checkout -b your-feature-name

# 2. Make your changes and test them

# 3. Commit your changes
git add .
git commit -m "Add feature: brief description"

# 4. Push to GitHub
git push origin your-feature-name

# 5. Create a Pull Request on GitHub
```

### If Not Using Git

1. Make your changes
2. Test thoroughly
3. Email the changed files with:
   - Description of what you changed
   - Why you made the change
   - Screenshots if UI changed

## Code Style Guidelines

### Keep It Simple

**Good:**
```python
def get_players(position):
    """Get all players for a position."""
    return df[df['position'] == position]
```

**Too Complex:**
```python
def get_players_with_advanced_filtering_and_sorting(
    position, min_points=0, max_points=999, sort_by='points'
):
    # Don't over-engineer simple functions
```

### Write Clear Comments

```python
# Good - explains WHY
# ESPN uses stat ID 53 for receptions (not documented anywhere)
receptions = stats.get('53', 0)

# Bad - states the obvious
# Get receptions from stats
receptions = stats.get('53', 0)
```

### Use Meaningful Names

```python
# Good
def calculate_fantasy_points(yards, touchdowns):
    return (yards * 0.1) + (touchdowns * 6)

# Bad
def calc(y, t):
    return (y * 0.1) + (t * 6)
```

## Common Questions

### Do I need to know Python?

**Basic contributions:** No - you can improve docs, test, and suggest features

**Code contributions:** Some Python helps, but simple changes are beginner-friendly

### What if I break something?

Don't worry! Test locally first. If something breaks:
1. The app will show an error message
2. Read the error (it usually tells you what's wrong)
3. Undo your change and try again
4. Ask for help in Issues

### How do I get help?

1. Check QUICKSTART.md and README.md
2. Check TESTING.md for common issues
3. Open an Issue on GitHub with:
   - What you're trying to do
   - What error you're seeing
   - Your operating system

### Can I add my own ideas?

**Yes!** Some ideas to get started:
- Add charts/graphs using Plotly
- Add player comparison tool
- Add injury status integration
- Add team defense rankings
- Add weather data
- Add news feed
- Add dark mode
- Add more positions (K, DST)

## Recognition

All contributors will be listed in the README.md!

## Code of Conduct

- Be respectful and welcoming
- Help others learn
- Ask questions - there are no dumb questions
- Share knowledge
- Give constructive feedback

## Resources for Learning

### Python Basics
- [Python.org Tutorial](https://docs.python.org/3/tutorial/)
- [Real Python](https://realpython.com/)

### Streamlit (UI Framework)
- [Streamlit Docs](https://docs.streamlit.io/)
- [Streamlit Gallery](https://streamlit.io/gallery)

### Pandas (Data Manipulation)
- [Pandas Getting Started](https://pandas.pydata.org/getting_started.html)

### Git/GitHub
- [GitHub Hello World](https://guides.github.com/activities/hello-world/)
- [Git Basics](https://git-scm.com/book/en/v2/Getting-Started-Git-Basics)

---

**Thank you for contributing to FFPy! Every contribution, no matter how small, makes this project better for everyone.**
