# Testing Guide for FFPy

This guide will help you test the Fantasy Football Projections app and verify that everything is working correctly.

## Quick Test (30 seconds)

### Step 1: Run the App

**Windows:**
```bash
run.bat
```

**Linux/macOS:**
```bash
make run
```

**Any platform:**
```bash
uv run streamlit run src/ffpy/app.py
```

### Step 2: Verify in Browser

The app should automatically open at `http://localhost:8501`. You should see:

1. **Title:** "Fantasy Football Point Projections" with a football emoji
2. **Sidebar:** Filters and controls on the left
3. **Main area:** Player projections table

### Step 3: Test Real-Time Data Toggle

In the sidebar:

1. **Toggle ON** "Use Real-Time Data"
   - You should see "API: ESPN" at the bottom of the sidebar
   - The table should show real NFL players

2. **Toggle OFF** "Use Real-Time Data"
   - The table should show sample data
   - You'll see Patrick Mahomes, Josh Allen, etc.

3. **Toggle back ON** to use real data

### Step 4: Test Filters

**Week Selection:**
- Change the week dropdown (1-18)
- Data should update immediately (cached for 1 hour)

**Position Filter:**
- Select "QB" - should show only quarterbacks
- Select "RB" - should show only running backs
- Select "WR" - should show only wide receivers
- Select "TE" - should show only tight ends
- Select "All Positions" - should show all players

**Player Count:**
- Use the slider to change player count (5-50)
- Table should resize immediately

## Testing Different APIs

### Test 1: ESPN API (Free - Default)

1. Check your `.env` file has:
   ```
   API_PROVIDER=espn
   ```

2. Run the app
3. Enable "Use Real-Time Data"
4. You should see:
   - Real NFL players
   - Current season data
   - "API: ESPN" in sidebar

### Test 2: SportsDataIO API (If you have a key)

1. Edit `.env` file:
   ```
   API_PROVIDER=sportsdata
   SPORTSDATA_API_KEY=your_actual_key_here
   ```

2. Restart the app
3. Enable "Use Real-Time Data"
4. You should see:
   - "API: SPORTSDATA" in sidebar
   - More detailed projections

### Test 3: Fallback to Sample Data

1. Edit `.env` file:
   ```
   API_PROVIDER=invalid_api
   ```

2. Restart the app
3. Enable "Use Real-Time Data"
4. You should see:
   - Warning message: "Unable to fetch real-time data. Using sample data."
   - Sample players displayed

5. Change back to `espn` when done

## Common Issues & Solutions

### Issue: "Module not found" error

**Solution:** Install dependencies
```bash
uv sync
```

### Issue: App won't start

**Solution:** Check if port 8501 is already in use
```bash
# Windows
netstat -ano | findstr :8501

# Linux/macOS
lsof -i :8501
```

Kill the process or use a different port:
```bash
uv run streamlit run src/ffpy/app.py --server.port 8502
```

### Issue: No data showing

**Solution:** Check your internet connection. ESPN API requires internet access.

### Issue: API key not working (SportsDataIO)

**Solution:**
1. Verify the key is correct in `.env`
2. Check you have API calls remaining (free tier = 1000/month)
3. Switch back to ESPN: `API_PROVIDER=espn`

## Verifying Configuration

Run this command to check your setup:

```bash
uv run python -c "from ffpy.config import Config; print('API Provider:', Config.get_api_provider()); print('Season:', Config.NFL_SEASON); print('Cache TTL:', Config.CACHE_TTL, 'seconds')"
```

**Expected output:**
```
API Provider: espn
Season: 2025
Cache TTL: 3600 seconds
```

## Performance Testing

### Cache Test

1. Run the app
2. Select Week 1, position "QB"
3. Note the load time
4. Change to "RB" and back to "QB"
5. Should load instantly (cached)
6. Wait 1 hour or restart app to clear cache

### API Rate Limit Test

1. Enable real-time data
2. Rapidly change weeks multiple times
3. Data should still load (thanks to caching)
4. First request per week is cached for 1 hour

## Testing Checklist

Use this checklist to verify all features work:

- [ ] App starts successfully
- [ ] Browser opens automatically to localhost:8501
- [ ] Sidebar shows all filters
- [ ] "Use Real-Time Data" toggle works
- [ ] API provider displays correctly in sidebar
- [ ] Week selection works (1-18)
- [ ] Position filters work (QB, RB, WR, TE, All)
- [ ] Player count slider works (5-50)
- [ ] Table displays player data correctly
- [ ] Position-specific stats show correctly
- [ ] Sample data toggle works
- [ ] Real-time data loads from ESPN
- [ ] Caching works (instant re-loads)
- [ ] App handles API errors gracefully

## Advanced Testing (For Developers)

### Test API Integration Directly

```python
# Test ESPN Integration
uv run python -c "
from ffpy.integrations import ESPNIntegration
api = ESPNIntegration()
df = api.get_projections(week=1, season=2025)
print(f'Loaded {len(df)} players')
print(df.head())
"
```

### Test Configuration

```python
# Test Config
uv run python -c "
from ffpy.config import Config
print(Config.debug_config())
"
```

### Test Data Layer

```python
# Test Data with Caching
uv run python -c "
from ffpy.data import get_projections
import time

# First call (hits API)
start = time.time()
df1 = get_projections(week=1, use_real_data=True)
t1 = time.time() - start
print(f'First call: {t1:.2f}s - {len(df1)} players')

# Second call (cached)
start = time.time()
df2 = get_projections(week=1, use_real_data=True)
t2 = time.time() - start
print(f'Cached call: {t2:.2f}s - {len(df2)} players')
print(f'Speedup: {t1/t2:.1f}x faster')
"
```

## Reporting Issues

If you encounter problems:

1. Check this testing guide first
2. Review the README.md
3. Verify your `.env` configuration
4. Check you have internet connection
5. Try switching to sample data mode
6. Report issues with:
   - Error message (full text)
   - Your `.env` configuration (remove API keys!)
   - Operating system and Python version
   - Steps to reproduce

## Success Criteria

The app is working correctly if:

1. ✓ App starts without errors
2. ✓ Real-time data loads from ESPN
3. ✓ All filters and controls work
4. ✓ Data updates when filters change
5. ✓ Caching improves performance
6. ✓ Fallback to sample data works when needed
7. ✓ UI is responsive and clear

**If all checks pass - you're good to go!**
