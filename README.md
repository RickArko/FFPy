# FFPy - Fantasy Football Point Projections

A web application for viewing fantasy football point projections by position and week. Built with Python, Streamlit, and uv.

## Quick Start (2 Minutes)

**New users - Get started in 3 commands:**

```bash
# 1. Install dependencies
uv sync

# 2. Run the app
uv run streamlit run src/ffpy/app.py

# 3. Open your browser to http://localhost:8501
```

**That's it!** The app works immediately with free ESPN data (no API key needed).

**Windows users can use:**
```bash
install.bat    # Install
run.bat        # Run
```

## Features

- View top projected players by position (QB, RB, WR, TE)
- Filter projections by NFL week (1-18)
- Adjustable player display count
- Position-specific statistics
- Clean, responsive interface
- Position breakdown view showing top 5 players per position

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

To install uv:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Installation

### One-Line Install

**Linux/macOS:**
```bash
make install
```

**Windows:**
```bash
install.bat
```

**Cross-platform (if make is not available):**
```bash
uv sync
```

This will:
1. Create a virtual environment
2. Install all dependencies (Streamlit, Pandas, Requests, python-dotenv)
3. Set up the project for development

### API Configuration (Optional)

The app works out of the box with **ESPN's free API** (no signup required). For better data quality and reliability, you can configure a paid API.

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Choose your API provider:**

   **Option A: ESPN (Default - Free)**
   - No configuration needed!
   - Uses unofficial ESPN API
   - Good for development and testing

   **Option B: SportsDataIO (Recommended for Production)**
   - Sign up at [https://sportsdata.io/](https://sportsdata.io/)
   - Choose NFL subscription (Free tier: 1000 calls/month)
   - Copy your API key
   - Edit `.env`:
     ```bash
     API_PROVIDER=sportsdata
     SPORTSDATA_API_KEY=your_actual_api_key_here
     ```

3. **Verify your setup:**
   - The app sidebar will show which API is active
   - Toggle "Use Real-Time Data" to switch between API and sample data

## Running the Application

### Start the App

**Linux/macOS:**
```bash
make run
```

**Windows:**
```bash
run.bat
```

**Cross-platform:**
```bash
uv run streamlit run src/ffpy/app.py
```

The app will open in your default browser at `http://localhost:8501`

### Development Mode

For auto-reload on file changes:

**Linux/macOS:**
```bash
make dev
```

**Cross-platform:**
```bash
uv run streamlit run src/ffpy/app.py --server.runOnSave=true
```

## Project Structure

```
FFPy/
├── src/
│   └── ffpy/
│       ├── __init__.py              # Package initialization
│       ├── app.py                   # Main Streamlit application
│       ├── data.py                  # Data fetching and caching
│       ├── config.py                # Environment configuration
│       └── integrations/
│           ├── __init__.py          # Integrations package
│           ├── base.py              # Base API integration class
│           ├── espn.py              # ESPN API integration
│           └── sportsdata.py        # SportsDataIO integration
├── .env.example                     # Environment template
├── .gitignore                       # Git ignore rules
├── pyproject.toml                   # Project dependencies and metadata
├── Makefile                         # Build commands (Linux/macOS)
├── install.bat                      # Windows installation script
├── run.bat                          # Windows run script
└── README.md                        # This file
```

## Usage

1. **Toggle Data Source**: Enable "Use Real-Time Data" for live projections or disable for sample data
2. **Select Week**: Use the sidebar to choose an NFL week (1-18)
3. **Filter by Position**: Choose a specific position (QB, RB, WR, TE) or view all positions
4. **Adjust Display Count**: Use the slider to show between 5-50 players
5. **View Statistics**: See position-specific stats like passing yards, rushing yards, receptions, etc.
6. **Position Breakdown**: When viewing all positions, scroll down to see top 5 players per position
7. **Check API Status**: The sidebar shows which API provider is currently active

## Real-Time Data

The app now supports **real-time fantasy football data** from multiple sources:

### Supported APIs
- **ESPN Fantasy API** (Free, no auth required)
  - Default option, works immediately
  - Unofficial API, may have rate limits

- **SportsDataIO** (Paid, official)
  - Free tier: 1000 API calls/month
  - Includes official projections, stats, injuries
  - More reliable than unofficial sources

### Caching
- API responses are cached for 1 hour (configurable in `.env`)
- Reduces API calls and improves performance
- Clear cache by restarting the app

### Fallback System
1. Tries configured API (SportsDataIO if set up)
2. Falls back to ESPN if primary fails
3. Uses sample data if all APIs fail

## Available Commands

**Linux/macOS:**
- `make install` - Install dependencies
- `make run` - Run the application
- `make dev` - Run in development mode
- `make clean` - Remove build artifacts
- `make help` - Show available commands

**Windows:**
- `install.bat` - Install dependencies
- `run.bat` - Run the application
- `uv run streamlit run src/ffpy/app.py` - Direct run command

## Development

To extend this application:

1. **Add more API providers**: Create new integrations in `src/ffpy/integrations/`
   - Implement `BaseAPIIntegration` class
   - Add configuration to `.env.example`
   - Update `data.py` to support new provider

2. **Add more positions**: Include DST, K positions
   - Update position filters in integrations
   - Modify display logic in `app.py`

3. **Add database storage**: Store historical projections
   - SQLite for local development
   - PostgreSQL for production (Supabase/Neon)

4. **Historical analysis**: Add charts and trends using Plotly or Altair
5. **User authentication**: Add user accounts to save custom projections
6. **Export functionality**: Allow users to export projections to CSV
7. **Comparison tools**: Compare projections from multiple sources

## Dependencies

- **streamlit** >= 1.40.0 - Web application framework
- **pandas** >= 2.2.0 - Data manipulation and analysis
- **requests** >= 2.31.0 - HTTP library for API calls
- **python-dotenv** >= 1.0.0 - Environment variable management

## Contributing

This is a fun project for learning. Feel free to extend and modify as needed.

## License

MIT License - Feel free to use this for your fantasy football leagues!

## Future Enhancements

- ✅ ~~Integration with real fantasy football APIs~~ (DONE)
- Database storage for historical projections
- Machine learning projection models
- Weekly accuracy tracking against actual results
- Player news and injury updates integration
- Customizable scoring systems (PPR, Standard, Half-PPR)
- Draft helper mode with ADP rankings
- Waiver wire recommendations
- Automated data refresh with scheduled jobs
- Trade analyzer
- Lineup optimizer
