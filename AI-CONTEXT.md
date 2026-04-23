# ** ~ AI-Condensed Context File ~ TOKEN-CONDENSED! DO NOT ALTER WITHOUT `/@ai-condense`**
---

## Project: FFPy — Fantasy Football Point Projections

**Description:** Streamlit web app + analytics toolkit for NFL fantasy football: projections, lineup optimization, pick'em analysis, ESPN league integration, play-by-play data ingestion via nflverse.

**Stack:** Python 3.13+, Streamlit, Pandas, Polars, DuckDB, SQLite, PuLP (ILP), Plotly, nflreadpy, uv build/package manager.

**Entry point:** `ffpy.app:main` → `uv run streamlit run src/ffpy/app.py`

---

## Repo Layout

```
FFPy/
├── src/ffpy/
│   ├── __init__.py            # exports main
│   ├── app.py                 # Streamlit main app (projections viewer)
│   ├── config.py              # Config class (env vars, .env loading)
│   ├── data.py                # Projections orchestration (sample/API/historical)
│   ├── database.py            # FFPyDatabase (SQLite ORM-like wrapper)
│   ├── projections.py         # HistoricalProjectionModel
│   ├── scoring.py             # ScoringConfig + calculate_fantasy_points
│   ├── optimizer.py           # Player/RosterConstraints/LineupOptimizer (ILP)
│   ├── pickem.py              # NFLGame/PickemAnalyzer (pick'em tools)
│   ├── nflverse_loader.py     # NFLVerseLoader (pbp ingestion)
│   ├── integrations/
│   │   ├── base.py            # BaseAPIIntegration ABC
│   │   ├── espn.py            # ESPNIntegration (free, unofficial)
│   │   ├── espn_league.py     # ESPNLeagueIntegration (private league data)
│   │   └── sportsdata.py      # SportsDataIntegration (paid)
│   ├── pages/                 # Streamlit multipage
│   │   ├── 1_🔍_Player_Comparison.py
│   │   └── 2_🏈_Pick'em_Analyzer.py
│   └── migrations/
│       ├── 001_initial_schema.sql        # players, actual_stats, projections, api_requests
│       └── 002_play_by_play_schema.sql   # games, plays, ftn_charting, snap_counts, player_id_mapping, data_loads
├── config/{scoring,roster}/*.json  # PPR/Half-PPR/Standard + standard/superflex/no_kicker_dst presets
├── scripts/                    # collect_historical_stats, generate_mock_2024_data, populate_plays
├── examples/                   # pickem, optimize_lineup, espn_league, play_analysis
├── tests/                      # test_scoring.py, test_optimizer.py (pytest)
├── demo_projections.py         # Historical projection demo
├── pyproject.toml              # uv project config
└── Makefile                    # install/run/dev/clean shortcuts
```

---

## Common Imports (declared once here; omitted from per-module listings below)

```python
import os, sys, json, logging, sqlite3, time
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Dict, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

import pandas as pd
import polars as pl
import numpy as np
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
from tqdm import tqdm
```

---

## src/ffpy/config.py — Configuration

```python
# Loads .env from project root (Path(__file__).parent.parent.parent / ".env")

class Config:
    """Application configuration loaded from environment variables."""
    API_PROVIDER = os.getenv("API_PROVIDER", "espn").lower()
    SPORTSDATA_API_KEY = os.getenv("SPORTSDATA_API_KEY", "")
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
    NFL_SEASON = int(os.getenv("NFL_SEASON", "2024"))
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hr default
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path.home() / ".ffpy" / "ffpy.db"))
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")

    @classmethod
    def get_api_provider(cls) -> str: ...
    @classmethod
    def is_sportsdata_configured(cls) -> bool:
        """True if API key set and != placeholder"""
    @classmethod
    def get_active_api_key(cls) -> str: ...
    @classmethod
    def debug_config(cls) -> dict:
        """Returns {api_provider, sportsdata_configured, nfl_season, cache_ttl}"""
```

---

## src/ffpy/app.py — Main Streamlit App

```python
def main():
    """Main entry point. Sidebar filters: data_source (Historical/API/Sample),
    week 1-18, position, top_n slider. Displays summary metrics, top players
    dataframe, position breakdown when 'All Positions'."""
    # Flow: data_source radio → use_historical_model / use_real_data flags
    # → get_projections(week, use_real_data, use_historical_model)
    # → filter_by_position → get_top_n_players → format_dataframe_for_display

def format_dataframe_for_display(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """Format the dataframe for display. Selects position-specific columns
    and renames to display-friendly labels."""
    # base_cols = [player, team, position, opponent, projected_points]
    # position_cols: QB→pass/rush stats, RB→rush/rec, WR/TE→rec only
```

---

## src/ffpy/data.py — Projections Orchestration

```python
def get_sample_projections(week: int = 1) -> pd.DataFrame:
    """Get sample fantasy football projections for a given week.
    Returns hardcoded DataFrame: ~20 players across QB/RB/WR/TE with
    projected_points and position-specific stats."""

def get_historical_projections(week: int = 1, lookback_weeks: int = 4) -> pd.DataFrame:
    """Get projections based on historical player performance.
    Uses HistoricalProjectionModel.generate_projections with recent_weight=0.6.
    Falls back to sample on empty or exception."""

@st.cache_data(ttl=Config.CACHE_TTL)
def get_projections(week: int = 1, use_real_data: bool = True,
                    use_historical_model: bool = False) -> pd.DataFrame:
    """Priority: historical model → sample (if !use_real_data) →
    SportsDataIO (if configured) → ESPN fallback → sample."""

def get_positions() -> List[str]:
    """Returns ['QB', 'RB', 'WR', 'TE']"""

def filter_by_position(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """Sorts by projected_points desc."""

def get_top_n_players(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """df.nlargest(n, 'projected_points')"""
```

---

## src/ffpy/database.py — FFPyDatabase (SQLite)

```python
class FFPyDatabase:
    """SQLite database for storing historical player stats + play-by-play."""

    def __init__(self, db_path: Optional[str] = None):
        """Defaults to Config.DATABASE_PATH. Auto-mkdirs, inits schema."""
        # Runs migrations/001_initial_schema.sql on init

    def init_database(self): ...
    def close(self): ...
    def __enter__(self) / __exit__: ...  # context manager

    # === PLAYER METHODS ===
    def get_or_create_player(self, name: str, team: str, position: str,
                             nfl_id: Optional[str] = None) -> int:
        """Lookup by nfl_id or (name, position). Updates team on match.
        Inserts new player if not found. Returns player_id."""

    # === ACTUAL STATS ===
    def store_actual_stats(self, df: pd.DataFrame, season: int, week: int,
                           source: str = "espn"):
        """Per-row: get_or_create_player → INSERT OR REPLACE into actual_stats."""

    def get_actual_stats(self, season: int, week: Optional[int] = None,
                         position: Optional[str] = None) -> pd.DataFrame:
        """SELECT from actual_stats JOIN players, ORDER BY actual_points DESC."""

    def get_player_history(self, player_name: str, num_weeks: int = 8) -> pd.DataFrame:
        """ORDER BY season DESC, week DESC LIMIT num_weeks."""

    # === API REQUEST TRACKING ===
    def check_api_request(self, source, season, week, request_type="actuals") -> bool:
        """True if successful request exists for TODAY."""
    def log_api_request(self, source, season, week, request_type, success,
                        error: Optional[str] = None): ...

    # === EXPORT/ANALYTICS ===
    def export_to_csv(self, output_dir: str = "backups"):
        """Exports players, actual_stats, projections, api_requests as timestamped CSVs."""

    def get_player_averages(self, player_name: str, num_weeks: int = 4) -> Dict[str, float]:
        """Returns {avg_points, avg_passing_yards, ..., consistency (std),
        games_played}."""

    # === PLAY-BY-PLAY (migration 002) ===
    def run_migration(self, migration_file: str):
        """Applies migrations/<migration_file> via executescript."""

    def store_games(self, games_df, show_progress=False) -> int:
        """game_columns allowlist; game_finished = home_score.notna() if scores exist."""

    def store_plays(self, plays_df, show_progress=True) -> int:
        """Batched insert (batch_size=1000). Optimizes SQLite: synchronous=OFF,
        journal_mode=MEMORY. On batch failure, falls back to row-by-row to
        skip UNIQUE-constraint duplicates. Restores settings in finally."""

    def store_ftn_charting(self, ftn_df, show_progress=True) -> int:
        """Filter out null play_id. Batched insert with duplicate skip."""

    def store_snap_counts(self, snaps_df, show_progress=True) -> int:
        """Filter null player_id/game_id. Batched insert with duplicate skip."""

    def log_data_load(self, load_type, season, week=None, status="started") -> int:
        """Returns load_id."""

    def update_data_load(self, load_id, status, records_loaded=0, error=None):
        """Updates status, duration_seconds via julianday math."""

    def get_latest_game_id(self, season: int) -> Optional[str]:
        """ORDER BY game_date DESC, game_id DESC LIMIT 1."""

    def get_plays(self, season, week=None, team=None, play_type=None, limit=None) -> pd.DataFrame:
        """Flexible filter on plays table. team matches posteam OR defteam."""

    def get_player_plays(self, player_name, season, play_types=None) -> pd.DataFrame:
        """WHERE passer_player_name OR rusher_player_name OR receiver_player_name = ?."""

    def get_player_targets(self, player_name, season, weeks=None) -> pd.DataFrame:
        """Receiver targets (play_type='pass'). Returns game_id, week, complete_pass,
        air_yards, yards_gained, touchdown, epa, wpa, cpoe."""

    def calculate_target_share(self, player_name, season, week=None) -> float:
        """CTE: player_targets / team_targets (team inferred from posteam of receiver).
        Returns 0.0 if no data."""

    def get_red_zone_stats(self, player_name, season, red_zone_yards=20) -> Dict[str, float]:
        """yardline_100 <= red_zone_yards. Returns {red_zone_plays, rushes, targets,
        tds, avg_epa}."""

    def get_game_snap_share(self, player_name, season, week=None) -> pd.DataFrame:
        """Returns offense_snaps/pct, defense_snaps/pct, st_snaps/pct."""
```

---

## src/ffpy/projections.py — HistoricalProjectionModel

```python
class HistoricalProjectionModel:
    """Generate projections based on player's historical performance."""

    def __init__(self, db: Optional[FFPyDatabase] = None):
        """Uses provided db or creates new FFPyDatabase()."""

    def generate_projections(self, season: int, week: int, lookback_weeks: int = 4,
                             recent_weight: float = 0.6) -> pd.DataFrame:
        """Projects all active players from recent data.
        Flow: db.get_actual_stats(season, week=max(1, week-lookback)) →
        unique players → project_player per player → DataFrame."""

    def project_player(self, player_name: str, season: int, target_week: int,
                       lookback_weeks: int = 4, recent_weight: float = 0.6) -> Optional[dict]:
        """Requires >= 2 games of history.
        Weighted-average stats [actual_points, passing_yards, passing_tds,
        rushing_yards, rushing_tds, receiving_yards, receiving_tds, receptions].
        Adds ±5% variance: np.random.uniform(0.95, 1.05).
        Consistency = std(actual_points)."""

    def _calculate_weights(self, n: int, recent_weight: float) -> np.ndarray:
        """Exponential decay (most recent highest).
        weights = [(1-recent_weight) + recent_weight * (i/(n-1)) for i in range(n)][::-1]
        Normalized to sum=1."""

    def get_player_projection(self, player_name, season, week) -> Optional[pd.DataFrame]:
        """Returns projection + recent_avg/high/low (last 5 weeks)."""
```

---

## src/ffpy/scoring.py — ScoringConfig & Points Calc

```python
@dataclass
class ScoringConfig:
    """Fantasy football scoring configuration."""
    name: str = "Standard"
    passing_yards_per_point: float = 25.0       # 1pt/25yd
    passing_td_points: float = 4.0
    interception_points: float = -2.0
    passing_2pt_conversion: float = 2.0
    rushing_yards_per_point: float = 10.0       # 1pt/10yd
    rushing_td_points: float = 6.0
    rushing_2pt_conversion: float = 2.0
    receiving_yards_per_point: float = 10.0
    receiving_td_points: float = 6.0
    reception_points: float = 0.0               # PPR=1.0, Half=0.5, Std=0.0
    receiving_2pt_conversion: float = 2.0
    fumble_lost_points: float = -2.0
    fumble_recovered_td: float = 6.0
    bonus_settings: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def ppr(cls) -> "ScoringConfig": ...         # reception_points=1.0
    @classmethod
    def half_ppr(cls) -> "ScoringConfig": ...    # reception_points=0.5
    @classmethod
    def standard(cls) -> "ScoringConfig": ...    # reception_points=0.0
    @classmethod
    def from_dict(cls, config: Dict) -> "ScoringConfig": ...
    @classmethod
    def from_json_file(cls, file_path: str) -> "ScoringConfig": ...
    def to_dict(self) -> Dict: ...
    def to_json_file(self, file_path: str): ...


def calculate_fantasy_points(stats: Dict[str, float],
                             scoring_config: ScoringConfig) -> float:
    """Calculate fantasy points for a player.

    Stats keys: passing_yards, passing_tds, interceptions, rushing_yards,
    rushing_tds, receiving_yards, receiving_tds, receptions,
    fumbles_lost (optional), fumbles_recovered_td, passing_2pt, rushing_2pt,
    receiving_2pt. All keys optional; missing = 0 contribution.

    Example: stats={passing_yards:300, passing_tds:2, interceptions:1,
    rushing_yards:50, rushing_tds:1}, ppr() → 29.0
    """
    # Points only added when stat > 0. Final rounded to 2 decimals.

def calculate_points_from_projection(projection: Dict, scoring_config: ScoringConfig) -> float:
    """Wrapper for projection dicts from HistoricalProjectionModel."""
```

---

## src/ffpy/optimizer.py — Lineup Optimization (ILP)

```python
class PlayerStatus(Enum):
    AVAILABLE = "available"
    INJURED = "injured"
    BYE = "bye"
    QUESTIONABLE = "questionable"   # still eligible
    OUT = "out"
    LOCKED = "locked"               # Already played this week

@dataclass
class Player:
    """Represents a fantasy football player with projection data."""
    name: str
    position: str                    # QB, RB, WR, TE, K, DST
    team: str
    projected_points: float
    status: PlayerStatus = PlayerStatus.AVAILABLE
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    consistency: Optional[float] = None  # std dev
    # detailed stats (optional): passing_yards, passing_tds, rushing_yards,
    # rushing_tds, receiving_yards, receiving_tds, receptions

    def is_available(self) -> bool:
        """True for AVAILABLE or QUESTIONABLE."""

@dataclass
class RosterConstraints:
    """Roster constraints for lineup optimization."""
    positions: Dict[str, int] = field(default_factory=dict)
    flex_positions: List[str] = field(default_factory=list)     # e.g. ['RB','WR','TE']
    num_flex: int = 0
    max_players_per_team: Optional[int] = None                  # stack limit
    total_starters: Optional[int] = None                        # auto: sum(positions) + num_flex
    locked_in: Set[str] = field(default_factory=set)
    locked_out: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """Auto-compute total_starters if None."""

    @classmethod
    def standard(cls):
        """QB:1, RB:2, WR:2, TE:1, K:1, DST:1, FLEX(RB/WR/TE):1 → 9 starters."""
    @classmethod
    def no_kicker_dst(cls):
        """QB:1, RB:2, WR:2, TE:1, FLEX:1 → 7 starters."""
    @classmethod
    def superflex(cls):
        """Standard + QB added to flex_positions."""
    @classmethod
    def from_dict(cls, config: Dict):
        """Handles list→set for locked_in/locked_out."""
    @classmethod
    def from_json_file(cls, file_path: str): ...
    def to_dict(self) -> Dict: ...
    def to_json_file(self, file_path: str): ...
    def get_required_positions(self) -> Dict[str, int]: ...

@dataclass
class LineupResult:
    starters: List[Player]
    bench: List[Player]              # sorted by projected_points desc
    total_points: float
    points_by_position: Dict[str, float]
    solve_time_ms: float
    is_optimal: bool
    improvement_vs_current: Optional[float] = None

    def get_starters_by_position(self) -> Dict[str, List[Player]]: ...


class LineupOptimizer:
    """Optimize lineups using Integer Linear Programming.

    Uses PuLP with CBC solver. Binary decision vars (start=1, sit=0).
    Maximize: sum(projected_points * x[player]) s.t. position/flex/lock constraints.
    """

    def __init__(self, constraints: RosterConstraints): ...

    def optimize(self, players: List[Player],
                 current_lineup: Optional[List[Player]] = None,
                 verbose: bool = False) -> LineupResult:
        """Flow:
        1. Filter to is_available() players (excludes INJURED/OUT/BYE/LOCKED).
        2. Create binary LpVariable per player.
        3. Objective: lpSum(points * x).
        4. Add constraints: position, flex, total_starters, locks, team_limits.
        5. Solve with PULP_CBC_CMD. Raises ValueError if not Optimal.
        6. Compute improvement_vs_current if provided.
        """

    def _add_position_constraints(self, prob, players, x):
        """FLEX-eligible positions: >= count (allows extras for flex).
        Non-flex: == count (exact). Raises ValueError if no eligible players."""

    def _add_flex_constraints(self, prob, players, x):
        """Total from flex-eligible positions == base_requirements + num_flex.
        Example: RB=2,WR=2,TE=1,FLEX=1 → RB+WR+TE total == 6."""

    def _add_total_starters_constraint(self, prob, players, x):
        """lpSum(x) == constraints.total_starters (if set)."""

    def _add_player_locks(self, prob, players, x):
        """Force x[name]==1 for locked_in; x[name]==0 for locked_out."""

    def _add_team_limits(self, prob, players, x):
        """lpSum(x for team) <= max_players_per_team (if set)."""

    def analyze_lineup(self, result: LineupResult) -> str:
        """Formatted text report: OPTIMAL LINEUP by position, Total Projected
        Points, Solve Time, Improvement %, TOP BENCH OPTIONS (top 5)."""
```

---

## src/ffpy/pickem.py — NFL Pick'em Analyzer

```python
@dataclass
class NFLGame:
    game_id: str
    week: int
    season: int
    home_team: str; away_team: str
    home_abbrev: str; away_abbrev: str
    game_time: Optional[datetime] = None
    home_score: Optional[int] = None; away_score: Optional[int] = None
    spread: Optional[float] = None   # positive = home favored
    over_under: Optional[float] = None
    home_win_prob: Optional[float] = None
    is_final: bool = False

    def get_favorite(self) -> Tuple[str, float]:
        """Returns (team_abbrev, abs(spread)). Home if spread>0, else away."""

    def get_winner(self) -> Optional[str]:
        """From final scores; returns 'TIE' on tie; None if not final."""


class PickemAnalyzer:
    """Analyze NFL games for pick'em competitions."""

    # ESPN team_abbrev → int id mapping (32 teams: ARI=22, ATL=1, ..., WAS=28)
    TEAM_IDS: Dict[str, int] = {...}
    ID_TO_TEAM = {v: k for k,v in TEAM_IDS.items()}

    def __init__(self, season: int = 2025): ...

    def get_weekly_games(self, week: int) -> List[NFLGame]:
        """GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
        params: seasontype=2, week, dates=season. Returns [] on error."""

    def _parse_espn_game(self, event: Dict, week: int) -> Optional[NFLGame]:
        """Parses competitors, scores, spread (e.g. 'KC -7' → normalizes to home
        perspective), over_under, home_win_prob from predictor.homeTeam.gameProjection."""

    def calculate_confidence_rankings(self, games: List[NFLGame]) -> pd.DataFrame:
        """Rank by confidence.
        confidence_score = spread_magnitude; if home_win_prob available:
          confidence_score = spread*0.6 + prob*100*0.4
        Sorted desc; confidence_points = N..1 (highest=N)."""

    def get_upset_candidates(self, games, threshold: float = 3.0) -> pd.DataFrame:
        """Games where spread <= threshold.
        upset_probability = min((threshold-spread)/threshold, 0.5)."""

    def simulate_pickem_strategy(self, games, strategy: str = "favorites") -> Dict:
        """strategy='favorites': pick all favorites (straight up)
        strategy='confidence': use calculate_confidence_rankings."""

    def format_weekly_picks(self, games, include_confidence: bool = True) -> str:
        """Human-readable formatted output (copy/paste ready)."""


def create_sample_pickem_data(week: int = 15) -> List[NFLGame]:
    """WARNING: FAKE DATA. 8 fictional matchups with spreads/win_probs
    for testing without API calls."""
```

---

## src/ffpy/nflverse_loader.py — Play-by-Play Ingestion

```python
# Requires: nflreadpy (installed via git from github.com/nflverse/nflreadpy)
import nflreadpy as nfl

class NFLVerseLoader:
    """Load NFL play-by-play data from nflverse."""

    def __init__(self, db: Optional[FFPyDatabase] = None):
        """Creates own FFPyDatabase if db is None. Context manager closes own."""

    def load_season(self, season: int, include_ftn: bool = True,
                    include_snaps: bool = True, verbose: bool = True) -> Dict[str, int]:
        """Full season load.
        Flow: db.log_data_load → nfl.load_pbp([season]) → extract_games →
        store_games → store_plays → if season>=2022 & include_ftn:
        nfl.load_ftn_charting → if season>=2012 & include_snaps: nfl.load_snap_counts
        → update_data_load('completed').
        Returns {plays, games, ftn, snaps}."""

    def load_historical(self, start_season: int, end_season: Optional[int] = None,
                        include_ftn=True, include_snaps=True, verbose=True) -> Dict[str, int]:
        """Iterates seasons, accumulates stats. end_season defaults to Config.NFL_SEASON."""

    def update_current_season(self, verbose=True) -> Dict[str, int]:
        """Incremental: filters pbp to game_id > latest_game (polars filter).
        Returns {plays, games} stored."""

    def _extract_games(self, pbp_df) -> pd.DataFrame:
        """Drop_duplicates by game_id; keeps 17 game-level fields."""

    def _store_games/_store_plays/_store_ftn_charting/_store_snap_counts:
        """Calls db.store_* with UNIQUE-constraint tolerance (returns 0 on dupes)."""

    def validate_data_quality(self, season: int) -> Dict:
        """Returns {total_plays, total_games, missing_player_ids (pass plays),
        missing_epa, invalid_downs (down not in 1-4), quality_score (0-100)}.
        quality_score = 100 - (issues/total_plays)*100."""


def setup_database(db_path: Optional[str] = None) -> FFPyDatabase:
    """Initialize DB + run migration 002_play_by_play_schema.sql."""
```

---

## src/ffpy/integrations/

### base.py
```python
class BaseAPIIntegration(ABC):
    """Abstract base class for fantasy football API integrations."""
    def __init__(self, api_key: Optional[str] = None): ...
    @abstractmethod
    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame: ...
    @abstractmethod
    def is_available(self) -> bool: ...
    def normalize_projections(self, raw_data: dict) -> pd.DataFrame:
        """Override in subclasses. Target columns: player, team, position,
        opponent, projected_points, week + position-specific stats."""
```

### espn.py
```python
class ESPNIntegration(BaseAPIIntegration):
    """ESPN Fantasy Football API (free, unofficial). No API key required."""
    BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"

    def is_available(self) -> bool: return True

    def get_actual_stats(self, week: int, season: int = 2024) -> pd.DataFrame:
        """GET {BASE}/seasons/{season}/segments/0/leaguedefaults/3
        params: scoringPeriodId=week, view=kona_player_info
        UA header to avoid blocks. Parses via _parse_espn_data(..., stat_source_id=0)."""

    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame:
        """Same URL, stat_source_id=1 (projections)."""

    def _parse_espn_data(self, data, week, stat_source_id=1) -> pd.DataFrame:
        """Iterates data['players']. Skips non-QB/RB/WR/TE (position_id not 1-4).
        Per player: name, team (from proTeamId), position, opponent, points,
        position-specific stats.
        NOTE: has bug — references undefined `projected_stats` (should be
        `extracted_stats`)."""

    def _extract_stats(self, stats, week, stat_source_id) -> dict:
        """Match entry where statSourceId==source AND scoringPeriodId==week.
        ESPN stat IDs: 3=pass_yds, 4=pass_tds, 20=int, 24=rush_yds, 25=rush_tds,
        42=rec_yds, 43=rec_tds, 53=receptions, 0=points."""

    def _get_position(self, position_id: int) -> str:
        """1:QB, 2:RB, 3:WR, 4:TE, 5:K, 16:D/ST"""

    def _get_team_abbr(self, team_id: int) -> str:
        """34-team map (1:ATL ... 34:HOU). Returns 'FA' if unknown."""
```

### espn_league.py
```python
class ESPNLeagueIntegration:
    """Access ESPN Fantasy Football private league data (roster, lineups,
    standings, matchups). Requires swid + espn_s2 cookies for private leagues."""

    BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"
    # slot_id → position
    LINEUP_SLOTS = {0:"QB", 2:"RB", 4:"WR", 6:"TE", 16:"D/ST", 17:"K",
                    20:"BENCH", 21:"IR", 23:"FLEX", 7:"OP"}

    def __init__(self, league_id: int, season: int = 2024,
                 swid: Optional[str] = None, espn_s2: Optional[str] = None):
        """Falls back to env ESPN_SWID / ESPN_S2 if not provided.
        Builds self.cookies dict."""

    def _make_request(self, params: Dict) -> Dict:
        """GET {BASE}/seasons/{season}/segments/0/leagues/{league_id}
        with cookies, UA header."""

    def get_league_info(self) -> Dict:
        """view=mSettings. Returns {name, size, scoring_type, roster_slots,
        playoff_teams, season}."""

    def get_all_teams(self) -> List[Dict]:
        """view=mTeam. Returns [{id, name, abbrev, owner, wins, losses, ties,
        points_for, points_against}]."""

    def get_team_roster(self, team_id: int, week: Optional[int] = None) -> pd.DataFrame:
        """view=mRoster [+ scoringPeriodId=week]. Returns per-player:
        player_id, player, position, team, lineup_slot, acquisition_type,
        injury_status."""

    def get_league_rosters(self, week=None) -> Dict[int, pd.DataFrame]:
        """All teams' rosters indexed by team_id."""

    def get_standings(self) -> pd.DataFrame:
        """Sorted by wins desc, points_for desc. Adds rank column."""

    def get_matchups(self, week: int) -> List[Dict]:
        """view=mMatchup. Returns [{home_team_id, away_team_id, home_score,
        away_score, winner}]."""

    def get_scoring_settings(self) -> Dict: ...

    def _get_scoring_type(self, settings) -> str:
        """Inspects scoringItems for stat_id=53 (receptions):
        1.0→'PPR', 0.5→'Half-PPR', else 'Standard'."""

    def _parse_roster_settings(self, settings) -> Dict[str, int]:
        """Extracts lineupSlotCounts; maps slot IDs via LINEUP_SLOTS;
        excludes BENCH/IR."""

    def _get_position(self, position_id) / _get_team_abbr(self, team_id):
        """Same maps as ESPNIntegration."""

def main():
    """CLI example using env vars ESPN_LEAGUE_ID, ESPN_SWID, ESPN_S2."""
```

### sportsdata.py
```python
class SportsDataIntegration(BaseAPIIntegration):
    """SportsDataIO NFL API (paid, official)."""
    BASE_URL = "https://api.sportsdata.io/v3/nfl"

    def is_available(self) -> bool:
        """True if api_key set and not placeholder."""

    def get_projections(self, week: int, season: int = 2025) -> pd.DataFrame:
        """Iterates [QB, RB, WR, TE] → _get_position_projections → concat."""

    def _get_position_projections(self, position, week, season) -> pd.DataFrame:
        """GET {BASE}/projections/json/PlayerGameProjectionStatsByWeek/{season}/{week}
        Header: Ocp-Apim-Subscription-Key=api_key.
        Handles 401 (invalid key), 403 (unauthorized endpoint)."""

    def _parse_sportsdata_response(self, data, position, week) -> pd.DataFrame:
        """Filters by Position; skips FantasyPointsPPR==0.
        Maps API fields: Name→player, Team, Position, Opponent,
        FantasyPointsPPR→projected_points. Position-specific stat mapping."""
```

---

## src/ffpy/pages/ — Streamlit Multipage

### 1_🔍_Player_Comparison.py
```python
def main():
    """Player comparison page. Sidebar: week, position filter, data source.
    Sidebar multiselect: up to 6 players (sorted by projected_points desc).
    4 tabs: Projections / Historical Performance / Scoring Systems / Stats Breakdown."""

def show_projections_comparison(data, week):
    """Metrics: highest, average, most_consistent (min std). Bar charts
    (horizontal) with plotly.express; Blues scale. Detailed comparison table."""

def show_historical_performance(players, current_week):
    """Calls db.get_player_history(name, num_weeks=8) per player.
    Line chart of actual_points by week. Summary: Games, Avg, High, Low, Std Dev."""

def show_scoring_system_comparison(data):
    """Recomputes fantasy points under PPR/Half-PPR/Standard for each player.
    Grouped bar chart; rankings per system; PPR vs Standard 'PPR Bonus' delta."""

def show_stats_breakdown(data):
    """Per-position stat columns (QB: pass/rush; RB: rush/rec; WR/TE: rec).
    Grouped bar chart per position; detail tables."""
```

### 2_🏈_Pick'em_Analyzer.py
```python
# st.set_page_config at module level
# Sidebar: season (2020-2025), week (1-18), use_sample_data, upset_threshold (1-7 pts)
# 4 tabs: Confidence Rankings / Straight Picks / Upset Candidates / Analytics

@st.cache_data(ttl=3600)
def get_games(week_num, use_sample, season_year):
    """If use_sample: create_sample_pickem_data; else analyzer.get_weekly_games.
    Shows error and stops if no games."""

# Tab 1: calculate_confidence_rankings → table + bar chart + format_weekly_picks code block
# Tab 2: simulate_pickem_strategy('favorites') → table + metrics + histogram of spreads
# Tab 3: get_upset_candidates → table + probability chart + strategy tips
# Tab 4: game stats + confidence tier breakdown (High≥7, Medium 3-7, Low<3) +
#        top picks + win prob box plot + all games details table
```

---

## src/ffpy/migrations/ — Database Schemas

### 001_initial_schema.sql
```sql
-- players: player_id PK, name, nfl_id UNIQUE, team, position CHECK IN
--   ('QB','RB','WR','TE','K','DST'), created_at, updated_at
CREATE TABLE players (...);

-- actual_stats: stat_id PK, player_id FK, season, week CHECK 1-18,
--   actual_points, passing_* (yards int, tds real, ints int), rushing_*,
--   receiving_*, opponent, home_away, game_date, source DEFAULT 'espn',
--   fetched_at. UNIQUE(player_id, season, week). CASCADE DELETE.
CREATE TABLE actual_stats (...);

-- projections: projection_id PK, player_id FK, season, week CHECK 1-18,
--   source CHECK IN ('espn','sportsdata','ffpy_model','sample'),
--   projected_points + per-stat fields (all REAL), opponent, home_away,
--   fetched_at. UNIQUE(player_id, season, week, source). CASCADE DELETE.
CREATE TABLE projections (...);

-- api_requests: request_id PK, source, season, week, request_type
--   ('actuals'|'projections'), success BOOL, error_message, created_at.
CREATE TABLE api_requests (...);

-- Indexes: idx_actual_stats_(player_season, week), idx_projections_*,
--   idx_api_requests_lookup, idx_players_(position, team).
```

### 002_play_by_play_schema.sql
```sql
-- games: game_id PK, old_game_id UNIQUE, season, season_type (REG/POST/PRE),
--   week, game_date, home/away_team + scores, roof/surface/temp/wind,
--   spread_line/total_line, location/stadium, game_finished.
CREATE TABLE games (...);

-- plays: play_id PK, game_id FK CASCADE, old_game_id, season/week/qtr/clock,
--   posteam/defteam, down/ydstogo/yardline_100/goal_to_go, play_type,
--   yards_gained, desc, shotgun/no_huddle/qb_* flags, pass/run location/gap,
--   -- Advanced nflfastR: epa, wpa, vegas_wpa, success, cpoe,
--   -- EPA components: air_epa, yac_epa, comp_air_epa, comp_yac_epa,
--   -- WPA components: air_wpa, yac_wpa, comp_air/yac_wpa,
--   -- xyac_* (expected yac), passer/rusher/receiver_player_name/id,
--   passing_yards/air_yards/yac/complete_pass/incomplete_pass/interception/sack/qb_hit,
--   receiving_yards, rushing_yards + lateral_*, touchdown/pass_/rush_/return_td,
--   extra_point_result/two_point_conv_result/field_goal_result/kick_distance,
--   posteam_/defteam_score_post, score_differential_post, wp/home_wp/vegas_wp,
--   timeouts_remaining, penalty_*, special_teams, fumble_*, safety,
--   solo_tackle_1/2_*, two_point_attempt, aborted_play, replay_*, series_*,
--   drive_* (result/play_count/top/first_downs/inside20/ended_with_score/...),
--   qb_epa, play_deleted, special_teams_play, st_play_type, end_* fields.
CREATE TABLE plays (...);

-- Indexes on plays: game, season_week, season_type, passer/rusher/receiver
--   player_id, posteam, defteam, play_type, down, (game_id, drive),
--   composite player_name + season, team + season + week.

-- ftn_charting: charting_id PK, play_id UNIQUE FK CASCADE,
--   n_offense_backfield, qb_location, is_play_action/screen_pass/rpo/trick_play/
--   qb_sneak/motion/no_huddle/qb_out_of_pocket/catchable_ball/contested_ball/
--   created_reception/drop/throw_away/interception_worthy, read_thrown,
--   n_blitzers, n_pass_rushers, is_qb_fault_sack, starting_hash.
CREATE TABLE ftn_charting (...);

-- snap_counts: snap_id PK, game_id FK CASCADE, pfr_game_id, player_id,
--   pfr_player_id, player_name, team, position, offense_snaps/pct,
--   defense_snaps/pct, st_snaps/pct, season, week, opponent.
--   UNIQUE(game_id, player_id).
CREATE TABLE snap_counts (...);

-- player_id_mapping: mapping_id PK, ffpy_player_id FK SET NULL,
--   gsis_id UNIQUE (primary nflverse), pfr_id, espn_id, yahoo_id, sleeper_id,
--   sportradar_id, fantasypros_id, player_name, position, team.
CREATE TABLE player_id_mapping (...);

-- data_loads: load_id PK, load_type (pbp/ftn/snaps/roster), season, week,
--   status (started/completed/failed), records_loaded, error_message,
--   started_at, completed_at, duration_seconds.
CREATE TABLE data_loads (...);
```

---

## config/ — JSON Presets

### scoring/ppr.json / half_ppr.json / standard.json
Matches ScoringConfig defaults; name + reception_points differ (1.0 / 0.5 / 0.0).

### roster/standard.json
```json
{"positions":{"QB":1,"RB":2,"WR":2,"TE":1,"K":1,"DST":1},
 "flex_positions":["RB","WR","TE"], "num_flex":1,
 "max_players_per_team":null, "total_starters":null,
 "locked_in":[], "locked_out":[]}
```
### roster/superflex.json — adds QB to flex_positions
### roster/no_kicker_dst.json — drops K/DST

---

## tests/ — pytest

### test_scoring.py
- **TestScoringConfig**: ppr/half_ppr/standard presets; to_dict/from_dict roundtrip; custom config.
- **TestCalculateFantasyPoints**: QB standard (300pYd+2pTD-1INT+20rYd=20pt), RB PPR, WR half-PPR, TE PPR, fumbles, zero/empty stats, dual-threat QB, 2pt conversions, custom rules, rounding (333/25=13.32), negative points possible.

### test_optimizer.py
- **TestPlayer**: creation, detailed projections, is_available (AVAILABLE/QUESTIONABLE→True; INJURED/OUT/BYE/LOCKED→False), repr.
- **TestRosterConstraints**: standard/superflex/no_kicker_dst presets; custom; auto total_starters; manual override; locked_in/out; to/from_dict roundtrip; get_required_positions.
- **TestLineupResult**: creation, with improvement, get_starters_by_position.
- **TestPlayerStatus**: enum values.
- **TestLineupOptimizer**: create_sample_players helper (17 players across positions). Tests: basic_optimization (9 starters), best-player selection, flex handling (6 RB+WR+TE), locked_in/out, injured excluded, team stack limits (max 2/team), no_kicker_dst (7 starters), improvement_calculation, bench sorting, analyze_lineup format, no_available error, insufficient_position error, points_by_position correctness.

---

## scripts/

### collect_historical_stats.py
```python
def collect_stats(season: int, start_week: int, end_week: int):
    """ESPN actuals collection loop. Uses db.check_api_request to skip
    already-fetched weeks. time.sleep(1) between requests to be nice to ESPN.
    Logs success/error via db.log_api_request."""
# argparse: --season, --start-week, --end-week
```

### generate_mock_2024_data.py
```python
# TOP_PLAYERS: 10 per position (QB/RB/WR/TE) with names and teams
def generate_{qb,rb,wr,te}_stats(player_name, week) -> dict:
    """Random realistic stats with ±30% variance. Points ~15-28 (QB),
    10-22 (RB), 8-20 (WR), 6-15 (TE)."""

def generate_season_data(season: int = 2024, weeks: int = 17):
    """For each week 1..weeks: for each position: for each of 10 players:
    generate stats and store_actual_stats(source='mock')."""
```

### populate_plays.py
```python
# CLI for NFLVerseLoader:
#   --migrate-only | --update | --season N | --start-season N --end-season M
#   --include-all (default True), --no-ftn, --no-snaps, --db-path, --quiet, --validate
def main():
    """Validates args (must specify action), inits setup_database (runs migration
    002), then dispatches: update → loader.update_current_season;
    single season → loader.load_season [+ validate_data_quality];
    range → loader.load_historical."""
```

---

## examples/

- **pickem_example.py**: End-to-end PickemAnalyzer demo: confidence rankings, all-favorites, upset candidates (threshold=3), format_weekly_picks. Falls back to create_sample_pickem_data on API failure.
- **optimize_lineup_example.py**: 6 scenarios — basic optimization, player locks (locked_in/out), injured/questionable handling, team stack limits (max 2/team), no_kicker_dst, improvement_vs_current.
- **espn_league_example.py**: ESPN private league flow: get_league_info → get_all_teams → get_team_roster(team_id, week) → ESPN projections → match to roster → build Player objects with injury_status → build RosterConstraints from league's roster_slots → optimize + recommend bench/start changes.
- **play_analysis_example.py**: 5 pbp analyses — QB TDs (passer_player_name+pass_touchdown=1), team red zone efficiency (yardline_100<=20), receiver target share (calculate_target_share + get_player_targets), QB weekly EPA (qb_dropback=1, GROUP BY week), database stats.

---

## demo_projections.py
Quick demo: FFPyDatabase stats → HistoricalProjectionModel.generate_projections(season=2024, week=18, lookback_weeks=4) → top 5 + position averages.

---

## pyproject.toml Highlights

```toml
[project]
name = "ffpy"
requires-python = ">=3.13"
dependencies = ["streamlit>=1.40", "pandas>=2.2", "requests>=2.31",
  "python-dotenv>=1.0", "polars>=1.36", "duckdb>=1.4", "pulp>=3.3",
  "plotly>=6.5", "nflreadpy", "tqdm>=4.67"]

[project.scripts]
ffpy = "ffpy.app:main"

[build-system]
requires = ["uv_build>=0.9.18,<0.10.0"]
build-backend = "uv_build"

[dependency-groups]
dev = ["coverage>=7.13", "pytest>=9.0", "ruff>=0.14"]
analysis = ["jupyter>=1.0", "matplotlib~=3.10", "seaborn>=0.13", "numpy>=1.26"]

[tool.ruff]
line-length = 110
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]

[tool.uv.sources]
nflreadpy = { git = "https://github.com/nflverse/nflreadpy" }
```

---

## Environment Variables (.env)

- `API_PROVIDER` = "espn" | "sportsdata" | "rapidapi" (default "espn")
- `SPORTSDATA_API_KEY`, `RAPIDAPI_KEY`
- `NFL_SEASON` (int, default 2024)
- `CACHE_TTL` (int seconds, default 3600)
- `DATABASE_PATH` (default ~/.ffpy/ffpy.db)
- `DATABASE_TYPE` (default "sqlite")
- `ESPN_LEAGUE_ID`, `ESPN_SWID`, `ESPN_S2`, `ESPN_TEAM_ID` — for ESPNLeagueIntegration

---

## Key Data Flows

1. **Projections viewer** (app.py): user → sidebar → `data.get_projections(week, use_real_data, use_historical_model)` → [historical → `HistoricalProjectionModel` → SQLite | API → integrations | sample hardcoded] → filter → display.
2. **Historical model**: `FFPyDatabase.get_actual_stats` → for each active player → `project_player` (weighted avg of last N weeks + ±5% variance) → DataFrame.
3. **Lineup optimization**: `List[Player]` → `LineupOptimizer.optimize` → PuLP CBC solver (ILP with position/flex/lock/team constraints) → `LineupResult`.
4. **Play-by-play ingestion**: `nflreadpy.load_pbp([season])` → polars/pandas conversion → `FFPyDatabase.store_games` + `store_plays` (batched, dup-tolerant) → optional FTN + snap_counts.
5. **Pick'em**: ESPN scoreboard API → parse events → `NFLGame` objects → confidence/favorites/upset strategies.

---

## Known Bug

`integrations/espn.py` `_parse_espn_data`: references undefined `projected_stats` variable when building position-specific fields for QB / RB / WR / TE player_record (should be `extracted_stats`). Will raise NameError when parsing actual player data.
