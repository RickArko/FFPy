# Quick Start Guide - For Everyone

**Get the app running in 2 minutes - No coding experience needed!**

This guide works for Windows, Mac, and Linux users.

---

## Step 1: Install uv (One-time setup)

**What is uv?** It's a tool that manages Python for you automatically.

### Windows

1. Open **PowerShell** or **Command Prompt**
2. Copy and paste this command:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. Press Enter and wait for it to finish
4. Close and reopen your terminal

### Mac / Linux

1. Open **Terminal**
2. Copy and paste this command:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Press Enter and wait for it to finish
4. Close and reopen your terminal

---

## Step 2: Install the App

Navigate to the project folder and run:

```bash
uv sync
```

**What does this do?** It installs Python and all required packages automatically.

**How long does it take?** 30 seconds to 2 minutes (only needed once)

---

## Step 3: Run the App

```bash
uv run streamlit run src/ffpy/app.py
```

**That's it!** Your browser will automatically open to the app.

---

## What You Should See

1. Terminal shows: `You can now view your Streamlit app in your browser`
2. Browser opens to: `http://localhost:8501`
3. You see: **Fantasy Football Point Projections** with player data

---

## Troubleshooting

### Error: "command not found: uv"

**Fix:** Close and reopen your terminal, then try again.

### Error: "Cannot open browser"

**Fix:** Manually open your browser and go to: `http://localhost:8501`

### Error: "Port already in use"

**Fix:** Stop other instances of the app or use a different port:
```bash
uv run streamlit run src/ffpy/app.py --server.port 8502
```
Then open: `http://localhost:8502`

### Nothing happens / Frozen

**Fix:** Press Ctrl+C to stop, then run the command again.

---

## Stopping the App

Press `Ctrl+C` in the terminal window.

---

## Running Again Later

You only need to run Step 2 (install) once. After that, just:

```bash
uv run streamlit run src/ffpy/app.py
```

---

## Windows Users - Even Simpler Option

Instead of typing commands, just double-click these files:

- **First time:** Double-click `install.bat`
- **Every time after:** Double-click `run.bat`

---

## That's It!

You now have a working Fantasy Football app with real-time NFL data.

**No Python installation required. No virtual environments. No complex setup.**

Just `uv sync` once, then `uv run streamlit run src/ffpy/app.py` every time.

---

## Next Steps (Optional)

Want to customize the data source? See the **API Configuration** section in README.md

Want to understand the code? See the **Project Structure** section in README.md

Want to contribute? See the **Development** section in README.md

---

## Questions?

- Check TESTING.md for detailed testing instructions
- Check README.md for advanced configuration
- The app works immediately with free ESPN data - no API key needed!
