"""Correlation-aware draft strategy engine.

Produces a ranked board of draft targets (default top 100) with human-readable
reasons, positional roster needs, and optional pick-slot recommendations. The
ranking blends four signals:

- positional **need** relative to the user's current roster
- **ADP value** at the user's pick slot(s)
- preseason **VORP** (projected points above positional replacement)
- weekly **correlation / stacking** with the user's existing starters

The same engine powers both the analysis notebook
(``notebooks/04_draft_strategy_macker.ipynb``) and the league web app's
``/api/leagues/{league_id}/draft-help`` endpoint.

Caveats:
- Preseason projections are recency-weighted historical fantasy points
  (not the in-season :class:`~ffpy.projections.EnhancedProjectionModel`).
- Rookies / low-history players fall back to ADP-tier positional priors and
  carry weaker correlation signals.
- Stack detection uses **current** NFL teams; correlation uses historical
  weekly series, which may span a player's prior teams.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ffpy.database import FFPyDatabase

logger = logging.getLogger(__name__)

SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]
DRAFTABLE_POSITIONS = SKILL_POSITIONS + ["K", "DST"]

# Starting lineup slots assumed for need calculation (standard 2-FLEX PPR).
DEFAULT_STARTER_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DST": 1}

# Module-level cache for the (large) Sleeper player map.
_SLEEPER_PLAYERS_CACHE: Dict[str, Any] = {"data": None, "fetched_at": 0.0}
_SLEEPER_CACHE_TTL = 6 * 60 * 60  # 6 hours


@dataclass
class DraftStrategyConfig:
    """Tunable parameters for the draft strategy engine."""

    # Blend weights (need not sum to 1.0; scores are relative).
    weight_need: float = 0.25
    weight_adp_value: float = 0.20
    weight_vorp: float = 0.30
    weight_corr: float = 0.25

    # Correlation / projection history.
    corr_seasons: List[int] = field(default_factory=lambda: [2023, 2024, 2025])
    season_weights: Dict[int, float] = field(default_factory=lambda: {2023: 0.15, 2024: 0.30, 2025: 0.55})
    ceiling_z: float = 1.28  # ~90th percentile lineup outcome
    min_weeks_for_corr: int = 8

    # Candidate pool.
    adp_platform: str = "fantasypros"
    top_n_per_position: int = 60
    corr_pool_size: int = 160  # cap candidates entering the correlation/ceiling loop

    # Pick slots (overall snake pick numbers). When provided, ADP value is
    # computed at the first pick slot and pick recommendations are produced.
    num_teams: int = 10
    pick_slots: Optional[List[int]] = None

    starter_slots: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_STARTER_SLOTS))


def _map_position(pos: Optional[str]) -> str:
    if not pos:
        return "?"
    pos = pos.upper()
    if pos in ("DEF", "D/ST", "DST"):
        return "DST"
    return pos


def _sleeper_players_cache_path() -> Path:
    from ffpy.config import Config

    cache_dir = Path(Config.DATABASE_PATH).expanduser().parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "sleeper_players.json"


def load_sleeper_players(force: bool = False) -> Dict[str, Any]:
    """Return the Sleeper player map, cached in memory and on disk.

    The Sleeper ``/players/nfl`` payload is large (~15 MB); caching avoids
    refetching on every request. Callers that only need a few IDs (e.g. league
    import) should not use this helper — it can exceed memory on small hosts.
    """
    now = time.time()
    cached = _SLEEPER_PLAYERS_CACHE.get("data")
    if not force and cached is not None and (now - _SLEEPER_PLAYERS_CACHE["fetched_at"]) < _SLEEPER_CACHE_TTL:
        return cached

    cache_path = _sleeper_players_cache_path()
    if not force and cache_path.exists():
        age = now - cache_path.stat().st_mtime
        if age < _SLEEPER_CACHE_TTL:
            with cache_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            _SLEEPER_PLAYERS_CACHE["data"] = data
            _SLEEPER_PLAYERS_CACHE["fetched_at"] = now
            return data

    from ffpy.integrations.sleeper import SleeperIntegration

    data = SleeperIntegration.get_players()
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)
    _SLEEPER_PLAYERS_CACHE["data"] = data
    _SLEEPER_PLAYERS_CACHE["fetched_at"] = now
    return data


def _resolve_roster(
    roster_json: Optional[str],
    provider: str,
    sleeper_players: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Resolve a team's stored roster into ``[{name, position, team}]``.

    Sleeper rosters store bare player IDs; ESPN/Yahoo store dicts.
    """
    entries = json.loads(roster_json or "[]")
    out: List[Dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("player") or entry.get("fullName") or entry.get("full_name")
            position = _map_position(entry.get("position"))
            team = entry.get("team") or ""
        else:
            # Bare ID (Sleeper) — legacy imports stored only IDs
            sp = (sleeper_players or {}).get(str(entry), {})
            name = (
                sp.get("full_name")
                or f"{(sp.get('first_name') or '').strip()} {(sp.get('last_name') or '').strip()}".strip()
                or sp.get("last_name")
            )
            if not name and sp.get("position") == "DEF":
                team_abbr = sp.get("team") or str(entry)
                name = f"{team_abbr} DST"
            position = _map_position(sp.get("position"))
            team = sp.get("team") or ""
        if name:
            out.append({"name": name, "position": position, "team": team})
    return out


class DraftStrategyEngine:
    """Builds a correlation-aware draft board for a league team."""

    def __init__(self, db: FFPyDatabase, config: Optional[DraftStrategyConfig] = None):
        self.db = db
        self.config = config or DraftStrategyConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(
        self,
        *,
        league: Dict[str, Any],
        teams: List[Dict[str, Any]],
        my_team_id: str,
        num_players: int = 100,
        sleeper_players: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate the draft board for ``my_team_id`` within ``league``.

        Returns a JSON-serializable dict with ``season``, ``roster_needs``,
        ``rankings`` (top ``num_players`` with reasons), ``picks`` (optional),
        and ``notes``.
        """
        cfg = self.config
        provider = (league.get("provider") or "").lower()
        season = int(league.get("season") or cfg.corr_seasons[-1])

        if provider == "sleeper" and sleeper_players is None:
            sleeper_players = load_sleeper_players()

        my_team = next((t for t in teams if t.get("team_id") == my_team_id), None)
        if my_team is None:
            raise ValueError(f"Team {my_team_id!r} not found in league")

        my_roster = _resolve_roster(my_team.get("roster_json"), provider, sleeper_players)
        rostered_names = self._all_rostered_names(teams, provider, sleeper_players)

        roster_needs, need_map = self._compute_needs(my_roster)

        adp_df, adp_season = self._load_adp(season)
        if adp_df.empty:
            return {
                "season": season,
                "roster_needs": roster_needs,
                "rankings": [],
                "picks": [],
                "notes": ["No ADP data available. Run `ffpy-db load-adp --season <year>`."],
            }

        candidates = self._build_candidate_pool(adp_df, rostered_names)
        weekly = self._load_weekly_points(cfg.corr_seasons)
        candidates = self._add_projections(candidates, weekly, adp_df)
        candidates = self._add_correlation(candidates, weekly, my_roster)
        candidates = self._score(candidates, need_map)

        board = candidates.sort_values("score", ascending=False).reset_index(drop=True)
        board["rank"] = board.index + 1

        rankings = self._rankings_payload(board.head(num_players), my_roster, need_map)
        picks = self._pick_recommendations(board, my_roster, need_map)

        notes = [
            f"ADP source: {cfg.adp_platform} ({adp_season}).",
            "Projections are recency-weighted historical fantasy points, not in-season projections.",
            "Correlation uses weekly scores from "
            f"{min(cfg.corr_seasons)}-{max(cfg.corr_seasons)}; rookies have limited signal.",
        ]
        if adp_season != season:
            notes.append(f"No {season} ADP found; fell back to {adp_season}.")

        return {
            "season": season,
            "roster_needs": roster_needs,
            "rankings": rankings,
            "picks": picks,
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Roster / needs
    # ------------------------------------------------------------------
    def _all_rostered_names(
        self,
        teams: List[Dict[str, Any]],
        provider: str,
        sleeper_players: Optional[Dict[str, Any]],
    ) -> set:
        names: set = set()
        for team in teams:
            for p in _resolve_roster(team.get("roster_json"), provider, sleeper_players):
                names.add(p["name"])
        return names

    def _compute_needs(self, my_roster: List[Dict[str, str]]):
        slots = self.config.starter_slots
        depth: Dict[str, int] = {}
        for p in my_roster:
            depth[p["position"]] = depth.get(p["position"], 0) + 1

        flex_depth = sum(depth.get(p, 0) for p in ("RB", "WR", "TE"))
        rows = []
        for slot, n_start in slots.items():
            if slot == "FLEX":
                rows.append(
                    {
                        "position": "FLEX",
                        "starters": n_start,
                        "depth": flex_depth,
                        "gap": round(max(0, n_start - max(0, flex_depth - 5)), 1),
                    }
                )
            else:
                rows.append(
                    {
                        "position": slot,
                        "starters": n_start,
                        "depth": depth.get(slot, 0),
                        "gap": max(0, n_start - depth.get(slot, 0)),
                    }
                )

        # Continuous need score per draftable position (higher = more need).
        need_map = {
            "QB": max(0.0, slots.get("QB", 1) - depth.get("QB", 0) + 0.5),
            "RB": max(0.0, slots.get("RB", 2) + slots.get("FLEX", 2) * 0.6 - depth.get("RB", 0)),
            "WR": max(0.0, slots.get("WR", 2) + slots.get("FLEX", 2) * 0.4 - depth.get("WR", 0)),
            "TE": max(0.0, slots.get("TE", 1) + slots.get("FLEX", 2) * 0.2 - depth.get("TE", 0)),
            "K": 0.3,
            "DST": 0.3,
        }
        # Rank positions by need for display.
        for r in rows:
            r["need_score"] = round(need_map.get(r["position"], 0.0), 2)
        return rows, need_map

    # ------------------------------------------------------------------
    # ADP / candidate pool
    # ------------------------------------------------------------------
    def _load_adp(self, season: int):
        cfg = self.config
        adp = self.db.get_adp(season=season, platform=cfg.adp_platform)
        used = season
        if adp.empty:
            adp = self.db.get_adp(season=season - 1, platform=cfg.adp_platform)
            used = season - 1
        if adp.empty:
            return pd.DataFrame(), used
        adp = adp.copy()
        adp["position"] = adp["position"].map(_map_position)
        adp = adp.sort_values("adp").drop_duplicates(subset=["player_name"], keep="first")
        return adp, used

    def _player_team_lookup(self) -> Dict[str, str]:
        players_df = pd.read_sql("SELECT name, team FROM players", self.db.conn)
        return {row["name"]: row["team"] for _, row in players_df.iterrows() if row.get("team")}

    def _build_candidate_pool(self, adp_df: pd.DataFrame, rostered_names: set) -> pd.DataFrame:
        cfg = self.config
        cand = adp_df[~adp_df["player_name"].isin(rostered_names)].copy()
        cand = cand[cand["position"].isin(DRAFTABLE_POSITIONS)]

        # ADP rows lack team — resolve from players table.
        team_lookup = self._player_team_lookup()
        cand["team"] = cand["player_name"].map(team_lookup).fillna("")

        parts = [cand[cand["position"] == pos].head(cfg.top_n_per_position) for pos in DRAFTABLE_POSITIONS]
        cand = pd.concat(parts, ignore_index=True).sort_values("adp").reset_index(drop=True)
        return cand

    # ------------------------------------------------------------------
    # Projections / VORP
    # ------------------------------------------------------------------
    def _load_weekly_points(self, seasons: List[int]) -> pd.DataFrame:
        frames = []
        for season in seasons:
            df = self.db.get_actual_stats(season=season)
            if df.empty:
                continue
            df = df[["player", "team", "position", "season", "week", "actual_points"]].copy()
            df["position"] = df["position"].map(_map_position)
            frames.append(df)
        if not frames:
            return pd.DataFrame(
                columns=["player", "team", "position", "season", "week", "actual_points", "week_key"]
            )
        out = pd.concat(frames, ignore_index=True)
        out["week_key"] = out["season"].astype(str) + "_w" + out["week"].astype(str)
        return out

    def _recency_weighted_ppg(self, weekly: pd.DataFrame, player_name: str):
        sub = weekly[weekly["player"] == player_name]
        if sub.empty:
            return np.nan, np.nan, 0
        w = sub["season"].map(self.config.season_weights).fillna(0.1)
        ppg = float(np.average(sub["actual_points"], weights=w))
        std = float(sub["actual_points"].std(ddof=0)) if len(sub) > 1 else 8.0
        if not np.isfinite(std):
            std = 8.0
        return ppg, std, int(len(sub))

    # Positional projection curve: PPG by within-position ADP rank
    # (top_ppg, floor_ppg, span-to-floor). A realistic monotonic decline so
    # deep/unknown players are not projected like startable starters.
    _CURVE = {
        "QB": (22.0, 11.0, 22),
        "RB": (17.5, 5.0, 48),
        "WR": (16.5, 5.0, 55),
        "TE": (12.5, 3.5, 22),
        "K": (9.0, 6.0, 20),
        "DST": (9.0, 5.0, 20),
    }
    # Cap on how much weight season history can take (vs market curve).
    _HISTORY_RAMP_WEEKS = 24
    _MAX_HISTORY_WEIGHT = 0.8

    def _curve_ppg(self, position: str, pos_rank: int) -> float:
        top, floor, span = self._CURVE.get(position, (10.0, 4.0, 40))
        return max(floor, top - (top - floor) * (pos_rank - 1) / max(1, span))

    def _add_projections(
        self, candidates: pd.DataFrame, weekly: pd.DataFrame, adp_df: pd.DataFrame
    ) -> pd.DataFrame:
        candidates = candidates.copy()
        # Within-position ADP rank for the market curve.
        candidates["pos_rank"] = (candidates.sort_values("adp").groupby("position").cumcount() + 1).reindex(
            candidates.index
        )

        rows = []
        for _, row in candidates.iterrows():
            name = row["player_name"]
            pos = row["position"]
            adp_rank = float(row["adp"])
            curve = self._curve_ppg(pos, int(row["pos_rank"]))
            hist_ppg, std, n_weeks = self._recency_weighted_ppg(weekly, name)

            if np.isnan(hist_ppg):
                ppg = curve
                std = std if not np.isnan(std) else 10.0
                source = "market"
            else:
                # Blend season history with the market curve; more history =>
                # trust history more (capped so the market anchors the scale).
                alpha = min(n_weeks / self._HISTORY_RAMP_WEEKS, 1.0) * self._MAX_HISTORY_WEIGHT
                ppg = alpha * hist_ppg + (1 - alpha) * curve
                source = "history" if alpha >= 0.4 else "blend"
            rows.append(
                {
                    "player_name": name,
                    "position": pos,
                    "team": row.get("team", ""),
                    "adp": adp_rank,
                    "projected_ppg": ppg,
                    "weekly_std": std,
                    "history_weeks": n_weeks,
                    "projection_source": source,
                }
            )
        cand = pd.DataFrame(rows)
        if cand.empty:
            return cand

        # VORP vs positional replacement level (ADP-rank proxy).
        repl_rank = {
            "QB": self.config.num_teams + 2,
            "RB": self.config.num_teams * 3,
            "WR": self.config.num_teams * 4,
            "TE": self.config.num_teams + 4,
            "K": self.config.num_teams + 3,
            "DST": self.config.num_teams + 2,
        }
        repl_ppg = {}
        for pos, rank in repl_rank.items():
            pos_rows = cand[cand["position"] == pos].sort_values("adp")
            if pos_rows.empty:
                repl_ppg[pos] = self._curve_ppg(pos, int(rank))
            else:
                idx = min(int(rank) - 1, len(pos_rows) - 1)
                repl_ppg[pos] = float(pos_rows.iloc[idx]["projected_ppg"])
        cand["replacement_ppg"] = cand["position"].map(repl_ppg)
        cand["vorp"] = cand["projected_ppg"] - cand["replacement_ppg"]
        return cand

    # ------------------------------------------------------------------
    # Correlation / ceiling
    # ------------------------------------------------------------------
    def _lineup_ceiling(self, players: List[str], weekly: pd.DataFrame) -> float:
        z = self.config.ceiling_z
        if not players:
            return 0.0
        mat = weekly[weekly["player"].isin(players)].pivot_table(
            index="week_key", columns="player", values="actual_points", aggfunc="mean"
        )
        mat = mat.reindex(columns=[p for p in players if p in mat.columns]).dropna(how="all")
        if mat.empty:
            return 0.0
        if mat.shape[1] < 2:
            means = mat.mean()
            mean = float(means.sum())
            sd = float(mat.std(ddof=0).fillna(8.0).sum())
            return mean + z * sd
        corr = mat.corr().fillna(0)
        stds = mat.std(ddof=0).fillna(8.0)
        cov = corr.values * np.outer(stds.values, stds.values)
        mean = float(mat.mean().sum())
        sd = float(np.sqrt(max(0.0, np.sum(cov))))
        return mean + z * sd

    def _add_correlation(
        self,
        candidates: pd.DataFrame,
        weekly: pd.DataFrame,
        my_roster: List[Dict[str, str]],
    ) -> pd.DataFrame:
        if candidates.empty:
            return candidates
        cfg = self.config

        starter_names = [p["name"] for p in my_roster if p["position"] in SKILL_POSITIONS]
        qb_teams = {p["team"] for p in my_roster if p["position"] == "QB" and p["team"]}

        # Limit the expensive ceiling loop to the strongest ADP candidates.
        pool = candidates.sort_values("adp").head(cfg.corr_pool_size).copy()

        if weekly.empty:
            candidates["avg_corr_with_starters"] = 0.0
            candidates["max_corr_with_starters"] = 0.0
            candidates["same_team_stack"] = candidates.apply(
                lambda r: r["team"] in qb_teams and r["position"] in ("WR", "TE", "RB"), axis=1
            )
            candidates["ceiling_lift"] = 0.0
            candidates["corr_score"] = candidates["same_team_stack"].map({True: 0.15, False: 0.0})
            candidates["neg_corr_player"] = None
            return candidates

        counts = weekly.groupby("player").size()
        valid = set(counts[counts >= cfg.min_weeks_for_corr].index)
        corr_universe = sorted(valid | set(starter_names) | set(pool["player_name"]))
        mat = weekly[weekly["player"].isin(corr_universe)].pivot_table(
            index="week_key", columns="player", values="actual_points", aggfunc="mean"
        )
        corr_matrix = mat.corr().fillna(0) if not mat.empty else pd.DataFrame()
        base_ceiling = self._lineup_ceiling(starter_names, weekly)

        rows = []
        for _, row in pool.iterrows():
            name = row["player_name"]
            pos = row["position"]
            team = row.get("team", "")
            starter_corrs = {}
            if name in corr_matrix.columns:
                for sn in starter_names:
                    if sn in corr_matrix.columns and sn != name:
                        starter_corrs[sn] = float(corr_matrix.loc[name, sn])
            avg_corr = float(np.mean(list(starter_corrs.values()))) if starter_corrs else 0.0
            max_corr = float(np.max(list(starter_corrs.values()))) if starter_corrs else 0.0
            neg_player = None
            if starter_corrs:
                worst = min(starter_corrs, key=starter_corrs.get)
                if starter_corrs[worst] < -0.15:
                    neg_player = worst
            same_team_stack = bool(team in qb_teams and pos in ("WR", "TE", "RB"))
            stack_bonus = 0.15 if same_team_stack else 0.0
            ceiling_lift = self._lineup_ceiling(starter_names + [name], weekly) - base_ceiling
            rows.append(
                {
                    "player_name": name,
                    "avg_corr_with_starters": avg_corr,
                    "max_corr_with_starters": max_corr,
                    "same_team_stack": same_team_stack,
                    "ceiling_lift": ceiling_lift,
                    "corr_score": avg_corr + stack_bonus + 0.05 * (ceiling_lift / 10.0),
                    "neg_corr_player": neg_player,
                }
            )
        corr_df = pd.DataFrame(rows)
        merged = candidates.merge(corr_df, on="player_name", how="left")
        merged["avg_corr_with_starters"] = merged["avg_corr_with_starters"].fillna(0.0)
        merged["max_corr_with_starters"] = merged["max_corr_with_starters"].fillna(0.0)
        merged["same_team_stack"] = merged["same_team_stack"].fillna(False).astype(bool)
        merged["ceiling_lift"] = merged["ceiling_lift"].fillna(0.0)
        merged["corr_score"] = merged["corr_score"].fillna(0.0)
        if "neg_corr_player" not in merged.columns:
            merged["neg_corr_player"] = None
        return merged

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(s: pd.Series) -> pd.Series:
        s = s.astype(float)
        lo, hi = s.min(), s.max()
        if hi == lo:
            return pd.Series(0.5, index=s.index)
        return (s - lo) / (hi - lo)

    # Streaming positions are draft-last; keep them on the board but ranked below
    # skill players regardless of ADP-value quirks.
    POSITION_WEIGHT = {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0, "K": 0.25, "DST": 0.25}

    def _score(self, candidates: pd.DataFrame, need_map: Dict[str, float]) -> pd.DataFrame:
        if candidates.empty:
            return candidates
        cfg = self.config
        candidates = candidates.copy()
        candidates["need_score"] = candidates["position"].map(need_map).fillna(0.5)
        # Dampen need: a deep roster has low needs everywhere, so need should be
        # a mild lean rather than a flat sweep of one position above all others.
        candidates["z_need"] = self._normalize(candidates["need_score"]) * 0.5
        candidates["z_vorp"] = self._normalize(candidates["vorp"])
        candidates["z_corr"] = self._normalize(candidates["corr_score"])

        # Provisional intrinsic value (need + projection + correlation) used to
        # judge ADP value. A player is "good value" when their ADP is later than
        # where their intrinsic value ranks them.
        intrinsic = (
            cfg.weight_need * candidates["z_need"]
            + cfg.weight_vorp * candidates["z_vorp"]
            + cfg.weight_corr * candidates["z_corr"]
        )
        candidates["_intrinsic"] = intrinsic
        value_rank = intrinsic.rank(ascending=False, method="first")
        # Positive => falls past intrinsic value (value pick); bounded both ways.
        candidates["adp_value"] = ((candidates["adp"] - value_rank) / max(1, cfg.num_teams)).clip(-3, 3)
        # Gate ADP value by quality so zero-value streamers don't float up.
        quality_gate = (candidates["z_vorp"] + 0.15).clip(0, 1)
        candidates["z_adp"] = self._normalize(candidates["adp_value"]) * quality_gate

        raw_score = intrinsic + cfg.weight_adp_value * candidates["z_adp"]
        pos_weight = candidates["position"].map(self.POSITION_WEIGHT).fillna(1.0)
        candidates["score"] = raw_score * pos_weight
        return candidates

    # ------------------------------------------------------------------
    # Payload / reasons
    # ------------------------------------------------------------------
    def _reasons_for(self, row: pd.Series, median_vorp: float, median_corr: float) -> List[str]:
        reasons: List[str] = []
        pos = row["position"]

        need = row.get("need_score", 0.0)
        if pos in ("RB", "WR", "TE", "QB") and need >= 1.5:
            reasons.append(f"Fills a clear {pos} need on your roster")
        elif pos in ("RB", "WR", "TE", "QB") and need >= 0.8:
            reasons.append(f"Adds {pos} depth you can use")

        if row.get("same_team_stack"):
            team = row.get("team", "")
            reasons.append(f"Stacks with your QB ({team}) — raises weekly ceiling")
        elif row.get("avg_corr_with_starters", 0.0) > max(0.05, median_corr):
            reasons.append(
                f"Positively correlated with your starters (r={row['avg_corr_with_starters']:.2f})"
            )

        if row.get("ceiling_lift", 0.0) > 1.0:
            reasons.append(f"+{row['ceiling_lift']:.1f} to your lineup ceiling")

        if row.get("vorp", 0.0) > max(0.0, median_vorp):
            reasons.append(f"{row['vorp']:+.1f} pts vs replacement {pos}")

        if row.get("adp_value", 0.0) > 0.5:
            reasons.append(f"ADP value — falls to ~pick {row['adp']:.0f}")

        if row.get("projection_source") == "market":
            reasons.append("Limited history — projection from positional market curve")
        elif row.get("projection_source") == "blend":
            reasons.append("Projection blends recent history with market curve")

        neg_player = row.get("neg_corr_player")
        if isinstance(neg_player, str) and neg_player:
            reasons.append(f"Note: negatively correlated with {neg_player}")

        if not reasons:
            reasons.append("Best available by blended value")
        return reasons

    def _tier_for(self, rank: int) -> str:
        if rank <= 12:
            return "Elite"
        if rank <= 24:
            return "Tier 1"
        if rank <= 48:
            return "Tier 2"
        if rank <= 72:
            return "Tier 3"
        return "Deep"

    def _rankings_payload(
        self,
        board: pd.DataFrame,
        my_roster: List[Dict[str, str]],
        need_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        if board.empty:
            return []
        median_vorp = float(board["vorp"].median())
        median_corr = float(board["avg_corr_with_starters"].median())
        out = []
        for _, row in board.iterrows():
            out.append(
                {
                    "rank": int(row["rank"]),
                    "player": row["player_name"],
                    "position": row["position"],
                    "team": row.get("team", ""),
                    "adp": round(float(row["adp"]), 1),
                    "projected_ppg": round(float(row["projected_ppg"]), 1),
                    "vorp": round(float(row["vorp"]), 1),
                    "correlation": round(float(row.get("avg_corr_with_starters", 0.0)), 3),
                    "ceiling_lift": round(float(row.get("ceiling_lift", 0.0)), 1),
                    "stack": bool(row.get("same_team_stack", False)),
                    "tier": self._tier_for(int(row["rank"])),
                    "score": round(float(row["score"]), 4),
                    "reasons": self._reasons_for(row, median_vorp, median_corr),
                }
            )
        return out

    def _pick_recommendations(
        self,
        board: pd.DataFrame,
        my_roster: List[Dict[str, str]],
        need_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        cfg = self.config
        if board.empty:
            return []
        median_vorp = float(board["vorp"].median())
        median_corr = float(board["avg_corr_with_starters"].median())

        if not cfg.pick_slots:
            # No known draft slot: surface the single best target.
            top = board.iloc[0]
            return [
                {
                    "pick_slot": None,
                    "label": "Best available target",
                    "player": top["player_name"],
                    "position": top["position"],
                    "team": top.get("team", ""),
                    "adp": round(float(top["adp"]), 1),
                    "reasons": self._reasons_for(top, median_vorp, median_corr),
                }
            ]

        remaining = board.copy()
        picks = []
        for slot in cfg.pick_slots:
            pool = remaining[remaining["adp"] >= slot - 0.5]
            if pool.empty:
                pool = remaining
            # Recompute ADP value at this slot.
            pool = pool.assign(slot_value=(pool["adp"] - slot) / max(1, cfg.num_teams))
            pool = pool.assign(
                slot_score=pool["score"] + cfg.weight_adp_value * self._normalize(pool["slot_value"])
            )
            choice = pool.sort_values("slot_score", ascending=False).iloc[0]
            picks.append(
                {
                    "pick_slot": int(slot),
                    "label": f"Pick #{int(slot)}",
                    "player": choice["player_name"],
                    "position": choice["position"],
                    "team": choice.get("team", ""),
                    "adp": round(float(choice["adp"]), 1),
                    "reasons": self._reasons_for(choice, median_vorp, median_corr),
                }
            )
            remaining = remaining[remaining["player_name"] != choice["player_name"]]
        return picks


__all__ = [
    "DraftStrategyConfig",
    "DraftStrategyEngine",
    "load_sleeper_players",
    "SKILL_POSITIONS",
    "DRAFTABLE_POSITIONS",
]
