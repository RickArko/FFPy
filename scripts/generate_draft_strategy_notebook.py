#!/usr/bin/env python3
"""Generate notebooks/04_draft_strategy_macker.ipynb from the draft strategy plan."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_PATH = Path(__file__).resolve().parents[1] / "notebooks" / "04_draft_strategy_macker.ipynb"


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


cells = [
    md(
        """# 04 — 2026 Draft Strategy for macker1477

**Goal:** Recommend three dynasty snake picks (#1, #20, #21) for *Tight ends and loose lips* by blending:

- positional roster need
- ADP / draft value
- preseason projected points (VORP)
- **weekly fantasy-point correlation** with macker's existing roster (stacking / ceiling lift)

**League context:** 10-team dynasty, 3-round snake, full PPR, lineup `QB / RB×2 / WR×2 / TE / FLEX×2 / K / DEF`.

**Caveats (read first):**
- Preseason projections use recency-weighted historical `actual_stats` (2023–2025), not the in-season `EnhancedProjectionModel`.
- Rookies / low-history players fall back to ADP-tier positional priors and carry weaker correlation signals.
- Stack detection uses **current** NFL teams; correlation uses historical weekly series (may span prior teams).
"""
    ),
    md(
        """## Setup

Prerequisites:

```bash
make bootstrap
uv run ffpy-db load-adp --season 2026   # already run if you followed the plan
```

Ensure macker's 2026 league is imported (`user_id = macker1477`)."""
    ),
    code(
        """import json
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore", category=FutureWarning)

_repo = Path.cwd()
while not (_repo / "pyproject.toml").exists() and _repo.parent != _repo:
    _repo = _repo.parent
sys.path.insert(0, str(_repo / "src"))

from ffpy.database import FFPyDatabase
from ffpy.draft_strategy import DraftStrategyConfig, DraftStrategyEngine
from ffpy.integrations.sleeper import SleeperIntegration
from ffpy.optimizer import LineupOptimizer, Player, RosterConstraints
from ffpy.scoring import ScoringConfig

sns.set_theme(style="whitegrid")
plt.rcParams["figure.dpi"] = 120

# ── Tunable league / draft config ──────────────────────────────────────────
USERNAME = "macker1477"
OWNER_ID = "1263503584687833088"
LEAGUE_ID = "sleeper:1312118348556828672"
DRAFT_SEASON = 2026
NUM_TEAMS = 10
PICK_SLOTS = [1, 20, 21]  # snake overall picks for macker
ADP_PLATFORM = "fantasypros"
ADP_SEASON_PRIMARY = 2026
ADP_SEASON_FALLBACK = 2025

# Blend weights (sum to 1.0)
WEIGHT_NEED = 0.25
WEIGHT_ADP_VALUE = 0.20
WEIGHT_VORP = 0.30
WEIGHT_CORR = 0.25

# Correlation / ceiling
CORR_SEASONS = [2023, 2024, 2025]
SEASON_WEIGHTS = {2023: 0.15, 2024: 0.30, 2025: 0.55}
CEILING_Z = 1.28  # ~90th percentile lineup outcome

SCORING = ScoringConfig.ppr()
LEAGUE_CONSTRAINTS = RosterConstraints(
    positions={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1},
    flex_positions=["RB", "WR", "TE"],
    num_flex=2,
)

STARTER_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DST": 1}
SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]
TOP_N_BY_POSITION = 60

print("Config loaded — picks", PICK_SLOTS, "| blend", {
    "need": WEIGHT_NEED,
    "adp": WEIGHT_ADP_VALUE,
    "vorp": WEIGHT_VORP,
    "corr": WEIGHT_CORR,
})"""
    ),
    md("## Helper functions"),
    code(
        """def normalize_series(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def map_position(pos: str) -> str:
    if pos in ("DEF", "D/ST"):
        return "DST"
    return pos


def load_adp_with_fallback(db: FFPyDatabase) -> tuple[pd.DataFrame, int]:
    adp = db.get_adp(season=ADP_SEASON_PRIMARY, platform=ADP_PLATFORM)
    season_used = ADP_SEASON_PRIMARY
    if adp.empty:
        adp = db.get_adp(season=ADP_SEASON_FALLBACK, platform=ADP_PLATFORM)
        season_used = ADP_SEASON_FALLBACK
    adp = adp.copy()
    adp["position"] = adp["position"].map(map_position)
    adp = adp.sort_values("adp").drop_duplicates(subset=["player_name"], keep="first")
    return adp, season_used


def bridge_sleeper_to_ffpy(
    sleeper_ids: list[str],
    sleeper_players: dict,
    players_df: pd.DataFrame,
) -> pd.DataFrame:
    gsis_map = {
        row["nfl_id"]: row
        for _, row in players_df.iterrows()
        if pd.notna(row.get("nfl_id")) and row.get("nfl_id")
    }
    rows = []
    for sid in sleeper_ids:
        sp = sleeper_players.get(str(sid), {})
        gsis = sp.get("gsis_id")
        mapped = gsis_map.get(gsis, {})
        rows.append(
            {
                "sleeper_id": str(sid),
                "player_name": sp.get("full_name") or sp.get("last_name") or str(sid),
                "position": map_position(sp.get("position") or "?"),
                "team": sp.get("team") or "",
                "ffpy_player_id": mapped.get("player_id"),
                "gsis_id": gsis,
            }
        )
    return pd.DataFrame(rows)


def load_weekly_points(db: FFPyDatabase, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        df = db.get_actual_stats(season=season)
        if df.empty:
            continue
        df = df[["player", "team", "position", "season", "week", "actual_points"]].copy()
        df["position"] = df["position"].map(map_position)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["week_key"] = out["season"].astype(str) + "_w" + out["week"].astype(str)
    return out


def recency_weighted_ppg(weekly: pd.DataFrame, player_name: str) -> tuple[float, float, int]:
    sub = weekly[weekly["player"] == player_name].copy()
    if sub.empty:
        return np.nan, np.nan, 0
    sub["w"] = sub["season"].map(SEASON_WEIGHTS).fillna(0.1)
    ppg = np.average(sub["actual_points"], weights=sub["w"])
    std = sub["actual_points"].std(ddof=0) if len(sub) > 1 else 8.0
    return float(ppg), float(std if pd.notna(std) else 8.0), len(sub)


def positional_replacement_levels(adp_df: pd.DataFrame, num_teams: int) -> dict[str, float]:
    repl_rank = {
        "QB": num_teams + 2,
        "RB": num_teams * 3,
        "WR": num_teams * 4,
        "TE": num_teams + 4,
        "K": num_teams + 3,
        "DST": num_teams + 2,
    }
    levels = {}
    for pos, rank in repl_rank.items():
        pos_adp = adp_df[adp_df["position"] == pos].sort_values("adp")
        if len(pos_adp) >= rank:
            levels[pos] = float(rank)
        elif not pos_adp.empty:
            levels[pos] = float(pos_adp.iloc[-1]["adp"])
        else:
            levels[pos] = 200.0
    return levels


def adp_tier_ppg(adp_rank: float, position: str) -> float:
    priors = {"QB": 18.0, "RB": 11.0, "WR": 10.5, "TE": 7.5, "K": 8.0, "DST": 7.0}
    base = priors.get(position, 9.0)
    # better ADP => higher projection; decay by rank
    return max(3.0, base * (1.4 - 0.004 * adp_rank))


def lineup_ceiling(players: list[str], weekly: pd.DataFrame, z: float = CEILING_Z) -> dict:
    if not players:
        return {"mean": 0.0, "sd": 0.0, "ceiling": 0.0}
    mat = weekly[weekly["player"].isin(players)].pivot_table(
        index="week_key", columns="player", values="actual_points", aggfunc="mean"
    )
    mat = mat.reindex(columns=players).dropna(how="all")
    if mat.empty or mat.shape[1] < 2:
        means = weekly[weekly["player"].isin(players)].groupby("player")["actual_points"].mean()
        mean = float(means.mean()) if not means.empty else 0.0
        sd = float(means.std(ddof=0)) if len(means) > 1 else 10.0
        return {"mean": mean, "sd": sd, "ceiling": mean + z * sd}
    corr = mat.corr().fillna(0)
    stds = mat.std(ddof=0).fillna(8.0)
    cov = corr.values * np.outer(stds.values, stds.values)
    mean = float(mat.mean().sum())
    sd = float(np.sqrt(np.sum(cov)))
    return {"mean": mean, "sd": sd, "ceiling": mean + z * sd}


def players_to_optimizer(players_df: pd.DataFrame) -> list[Player]:
    out = []
    for _, r in players_df.iterrows():
        out.append(
            Player(
                name=r["player_name"],
                position=r["position"],
                team=r.get("team", ""),
                projected_points=float(r.get("projected_ppg", 0.0)),
                consistency=float(r.get("weekly_std", 8.0)) if pd.notna(r.get("weekly_std")) else 8.0,
            )
        )
    return out


def optimize_lineup(players: list[Player], constraints: RosterConstraints):
    opt = LineupOptimizer(constraints)
    return opt.optimize(players)"""
    ),
    md("## 1. Resolve roster + ID bridge"),
    code(
        """db = FFPyDatabase()
sleeper_players = SleeperIntegration.get_players()
players_df = pd.read_sql("SELECT player_id, name, nfl_id, team, position FROM players", db.conn)

all_teams = db.get_league_teams(LEAGUE_ID, USERNAME)
macker_team = next(t for t in all_teams if t["owner_name"] == OWNER_ID)
macker_sleeper_ids = json.loads(macker_team.get("roster_json") or "[]")

roster_df = bridge_sleeper_to_ffpy(macker_sleeper_ids, sleeper_players, players_df)
roster_df["is_starter_candidate"] = roster_df["position"].isin(SKILL_POSITIONS + ["K", "DST"])

# All rostered player names in league (for candidate exclusion)
rostered_names: set[str] = set()
for team in all_teams:
    for sid in json.loads(team.get("roster_json") or "[]"):
        sp = sleeper_players.get(str(sid), {})
        name = sp.get("full_name") or sp.get("last_name")
        if name:
            rostered_names.add(name)

pos_counts = roster_df["position"].value_counts().to_dict()
print(f"macker roster ({len(roster_df)} players)")
display(roster_df[["player_name", "position", "team", "ffpy_player_id"]])

print("\\nPositional counts:", pos_counts)
need_rows = []
for pos, slots in STARTER_SLOTS.items():
    if pos == "FLEX":
        depth = sum(pos_counts.get(p, 0) for p in SKILL_POSITIONS if p != "QB")
        need_rows.append({"slot": pos, "starters": slots, "depth": depth, "gap": slots - depth})
    else:
        p = pos
        depth = pos_counts.get(p, 0)
        need_rows.append({"slot": pos, "starters": slots, "depth": depth, "gap": slots - depth})
need_df = pd.DataFrame(need_rows)
display(need_df)

# Existing stacks (same NFL team as a roster QB)
qb_teams = set(roster_df.loc[roster_df["position"] == "QB", "team"].dropna())
roster_df["stack_with_qb"] = roster_df.apply(
    lambda r: r["team"] in qb_teams and r["position"] in ("WR", "TE", "RB"), axis=1
)
print("Current stacks (skill player shares team with roster QB):")
display(roster_df.loc[roster_df["stack_with_qb"], ["player_name", "position", "team"]])"""
    ),
    md("## 2. Candidate pool (ADP minus rostered)"),
    code(
        """adp_df, adp_season_used = load_adp_with_fallback(db)
print(f"ADP loaded: {len(adp_df)} players (season {adp_season_used}, platform {ADP_PLATFORM})")

candidates = adp_df[~adp_df["player_name"].isin(rostered_names)].copy()
candidates = candidates[candidates["position"].isin(SKILL_POSITIONS + ["K", "DST"])]

# ADP rows lack team — join from players table, then Sleeper player DB by name
name_team = players_df[["name", "team"]].drop_duplicates("name").rename(columns={"name": "player_name"})
candidates = candidates.merge(name_team, on="player_name", how="left")
missing_team = candidates["team"].isna()
if missing_team.any():
    sleeper_by_name = {
        p.get("full_name"): p.get("team")
        for p in sleeper_players.values()
        if p.get("full_name")
    }
    candidates.loc[missing_team, "team"] = candidates.loc[missing_team, "player_name"].map(sleeper_by_name)
candidates["team"] = candidates["team"].fillna("")

# Keep top-N by position for tractability
parts = []
for pos in SKILL_POSITIONS + ["K", "DST"]:
    parts.append(candidates[candidates["position"] == pos].head(TOP_N_BY_POSITION))
candidates = pd.concat(parts, ignore_index=True).sort_values("adp")

print(f"Draftable candidates: {len(candidates)} (excluded {len(rostered_names)} rostered names)")
display(candidates.head(15)[["player_name", "position", "team", "adp"]])"""
    ),
    md("## 3. Preseason projections + VORP"),
    code(
        """weekly = load_weekly_points(db, CORR_SEASONS)
print(f"Weekly points rows: {len(weekly)} | players: {weekly['player'].nunique()}")

proj_rows = []
for _, row in candidates.iterrows():
    name = row["player_name"]
    pos = row["position"]
    adp_rank = float(row["adp"])
    ppg, std, n_weeks = recency_weighted_ppg(weekly, name)
    used_prior = False
    if np.isnan(ppg):
        ppg = adp_tier_ppg(adp_rank, pos)
        std = 10.0
        used_prior = True
    proj_rows.append(
        {
            "player_name": name,
            "position": pos,
            "team": row.get("team", ""),
            "adp": adp_rank,
            "projected_ppg": ppg,
            "weekly_std": std,
            "history_weeks": n_weeks,
            "projection_source": "prior" if used_prior else "history",
        }
    )

candidates = pd.DataFrame(proj_rows)

# VORP vs positional replacement (by ADP rank proxy)
repl = positional_replacement_levels(adp_df, NUM_TEAMS)
repl_ppg = {}
for pos, adp_rank in repl.items():
    pos_hist = candidates[candidates["position"] == pos].sort_values("adp")
    if not pos_hist.empty:
        idx = min(int(adp_rank) - 1, len(pos_hist) - 1)
        repl_ppg[pos] = float(pos_hist.iloc[idx]["projected_ppg"])
    else:
        repl_ppg[pos] = adp_tier_ppg(adp_rank, pos)

candidates["replacement_ppg"] = candidates["position"].map(repl_ppg)
candidates["vorp"] = candidates["projected_ppg"] - candidates["replacement_ppg"]

display(
    candidates.sort_values("vorp", ascending=False)
    .head(12)[["player_name", "position", "adp", "projected_ppg", "vorp", "projection_source"]]
)"""
    ),
    md("## 4. Weekly correlation + ceiling lift"),
    code(
        """# Correlation matrix on players with sufficient weekly history
hist_players = weekly.groupby("player").size()
valid_players = hist_players[hist_players >= 8].index.tolist()
corr_players = sorted(set(valid_players) | set(roster_df["player_name"]) | set(candidates["player_name"]))

mat = weekly[weekly["player"].isin(corr_players)].pivot_table(
    index="week_key", columns="player", values="actual_points", aggfunc="mean"
)
corr_matrix = mat.corr().fillna(0)

starter_names = roster_df.loc[roster_df["position"].isin(SKILL_POSITIONS), "player_name"].tolist()
base_lineup_stats = lineup_ceiling(starter_names, weekly)

corr_rows = []
qb_teams = set(roster_df.loc[roster_df["position"] == "QB", "team"].dropna())
for _, row in candidates.iterrows():
    name = row["player_name"]
    pos = row["position"]
    team = row.get("team", "")

    if name in corr_matrix.columns:
        starter_corrs = []
        for sn in starter_names:
            if sn in corr_matrix.columns and sn != name:
                starter_corrs.append(float(corr_matrix.loc[name, sn]))
        avg_corr = float(np.mean(starter_corrs)) if starter_corrs else 0.0
        max_corr = float(np.max(starter_corrs)) if starter_corrs else 0.0
    else:
        avg_corr, max_corr = 0.0, 0.0

    same_team_stack = team in qb_teams and pos in ("WR", "TE", "RB")
    stack_bonus = 0.15 if same_team_stack else 0.0

    trial_names = starter_names + [name]
    trial_stats = lineup_ceiling(trial_names, weekly)
    ceiling_lift = trial_stats["ceiling"] - base_lineup_stats["ceiling"]

    corr_rows.append(
        {
            "player_name": name,
            "avg_corr_with_starters": avg_corr,
            "max_corr_with_starters": max_corr,
            "same_team_stack": same_team_stack,
            "stack_bonus": stack_bonus,
            "ceiling_lift": ceiling_lift,
            "corr_score": avg_corr + stack_bonus + 0.05 * (ceiling_lift / 10.0),
        }
    )

corr_df = pd.DataFrame(corr_rows)
candidates = candidates.merge(corr_df, on="player_name", how="left")

print("Baseline starter-pool ceiling:", round(base_lineup_stats["ceiling"], 1))
display(
    candidates.sort_values("corr_score", ascending=False)
    .head(10)[["player_name", "position", "team", "avg_corr_with_starters", "same_team_stack", "ceiling_lift", "corr_score"]]
)"""
    ),
    md("## 5. Blended draft score"),
    code(
        """# Positional need score (higher = more need at that position)
depth = roster_df["position"].value_counts().to_dict()
flex_depth = sum(depth.get(p, 0) for p in ("RB", "WR", "TE"))
need_map = {
    "QB": max(0, STARTER_SLOTS["QB"] - depth.get("QB", 0) + 0.5),
    "RB": max(0, STARTER_SLOTS["RB"] + STARTER_SLOTS["FLEX"] * 0.6 - depth.get("RB", 0)),
    "WR": max(0, STARTER_SLOTS["WR"] + STARTER_SLOTS["FLEX"] * 0.4 - depth.get("WR", 0)),
    "TE": max(0, STARTER_SLOTS["TE"] + STARTER_SLOTS["FLEX"] * 0.2 - depth.get("TE", 0)),
    "K": 0.3,
    "DST": 0.3,
}
# RB-thin, WR-heavy roster => RB need highest
need_map["RB"] += 1.0
need_map["WR"] -= 0.5

candidates["need_score"] = candidates["position"].map(need_map).fillna(0.5)

# ADP value at pick #1 (positive when player ADP is later than slot => value)
candidates["adp_value_p1"] = (candidates["adp"] - PICK_SLOTS[0]) / NUM_TEAMS
candidates["adp_value_p20"] = (candidates["adp"] - PICK_SLOTS[1]) / NUM_TEAMS
candidates["adp_value_p21"] = (candidates["adp"] - PICK_SLOTS[2]) / NUM_TEAMS

for col in ["need_score", "vorp", "corr_score", "adp_value_p1", "adp_value_p20", "adp_value_p21"]:
    candidates[f"z_{col}"] = normalize_series(candidates[col])

candidates["score_pick1"] = (
    WEIGHT_NEED * candidates["z_need_score"]
    + WEIGHT_ADP_VALUE * candidates["z_adp_value_p1"]
    + WEIGHT_VORP * candidates["z_vorp"]
    + WEIGHT_CORR * candidates["z_corr_score"]
)
candidates["score_pick20"] = (
    WEIGHT_NEED * candidates["z_need_score"]
    + WEIGHT_ADP_VALUE * candidates["z_adp_value_p20"]
    + WEIGHT_VORP * candidates["z_vorp"]
    + WEIGHT_CORR * candidates["z_corr_score"]
)
candidates["score_pick21"] = (
    WEIGHT_NEED * candidates["z_need_score"]
    + WEIGHT_ADP_VALUE * candidates["z_adp_value_p21"]
    + WEIGHT_VORP * candidates["z_vorp"]
    + WEIGHT_CORR * candidates["z_corr_score"]
)

board = candidates.sort_values("score_pick1", ascending=False)
display(
    board.head(15)[
        [
            "player_name",
            "position",
            "team",
            "adp",
            "projected_ppg",
            "vorp",
            "same_team_stack",
            "corr_score",
            "score_pick1",
        ]
    ]
)"""
    ),
    md("## 6. Snake simulation (#1, #20, #21)"),
    code(
        """def simulate_snake_picks(board_df: pd.DataFrame, picks: list[int]) -> pd.DataFrame:
    remaining = board_df.sort_values("adp").copy()
    chosen = []

    for i, slot in enumerate(picks):
        # Players likely gone: ADP better (lower) than slot minus small noise
        gone = remaining[remaining["adp"] < slot - 0.5]
        pool = remaining[remaining["adp"] >= slot - 0.5]
        if pool.empty:
            pool = remaining

        score_col = {1: "score_pick1", 20: "score_pick20", 21: "score_pick21"}.get(slot, "score_pick1")
        pick = pool.sort_values(score_col, ascending=False).iloc[0]
        chosen.append(
            {
                "pick_slot": slot,
                "player_name": pick["player_name"],
                "position": pick["position"],
                "team": pick.get("team", ""),
                "adp": pick["adp"],
                "score": pick[score_col],
                "same_team_stack": pick.get("same_team_stack", False),
                "vorp": pick["vorp"],
                "corr_score": pick["corr_score"],
            }
        )
        remaining = remaining[remaining["player_name"] != pick["player_name"]]

    return pd.DataFrame(chosen)


picks_df = simulate_snake_picks(board, PICK_SLOTS)
print("Recommended picks:")
display(picks_df)

# Contingency tree for pick #1
pick1 = board.sort_values("score_pick1", ascending=False).iloc[0]
alt = board.sort_values("score_pick1", ascending=False).iloc[1]
print(f"If {pick1['player_name']} is gone at #1 -> consider {alt['player_name']} ({alt['position']})")

# Turn contingency (#20/#21)
turn_pool = board[board["adp"] >= PICK_SLOTS[1] - 1].sort_values("score_pick20", ascending=False)
print("\\nTop options if available at #20/#21 turn:")
display(turn_pool.head(8)[["player_name", "position", "adp", "score_pick20", "same_team_stack"]])"""
    ),
    md("## 7. Lineup optimizer before vs after picks"),
    code(
        """# Attach projections to roster for optimizer
roster_proj = roster_df.merge(
    candidates[["player_name", "projected_ppg", "weekly_std"]],
    on="player_name",
    how="left",
)
roster_proj["projected_ppg"] = roster_proj["projected_ppg"].fillna(6.0)
roster_proj["weekly_std"] = roster_proj["weekly_std"].fillna(8.0)

before_players = players_to_optimizer(roster_proj)
before_result = optimize_lineup(before_players, LEAGUE_CONSTRAINTS)

# Add recommended picks to pool
pick_names = picks_df["player_name"].tolist()
added = candidates[candidates["player_name"].isin(pick_names)].copy()
after_pool = pd.concat([roster_proj, added], ignore_index=True)
after_players = players_to_optimizer(after_pool)
after_result = optimize_lineup(after_players, LEAGUE_CONSTRAINTS)


def summarize_lineup(result, label: str):
    starters = result.starters
    total = result.total_points
    floor = sum(p.floor for p in starters)
    ceiling = sum(p.ceiling for p in starters)
    print(f"\\n{label}")
    print(f"  Projected starters: {total:.1f} pts")
    print(f"  Floor (approx):     {floor:.1f}")
    print(f"  Ceiling (approx):   {ceiling:.1f}")
    for p in starters:
        print(f"    {p.position:3} {p.name:24} {p.projected_points:5.1f}")


summarize_lineup(before_result, "Before draft (current roster)")
summarize_lineup(after_result, "After draft (+3 recommended picks)")

print(
    f"\\nOptimizer lift: {after_result.total_points - before_result.total_points:+.1f} projected starter points"
)"""
    ),
    md("## 8. Visualizations"),
    code(
        """# Correlation heatmap: roster starters + top 8 candidates
top_cands = board.head(8)["player_name"].tolist()
heat_players = starter_names + [p for p in top_cands if p not in starter_names]
heat_mat = corr_matrix.reindex(index=heat_players, columns=heat_players).fillna(0)

plt.figure(figsize=(10, 8))
sns.heatmap(heat_mat, cmap="RdBu_r", center=0, vmin=-0.5, vmax=0.5, square=True)
plt.title("Weekly fantasy-point correlation: roster + top candidates")
plt.tight_layout()
plt.show()

# ADP vs projection scatter
plot_df = board.head(40)
plt.figure(figsize=(9, 6))
sns.scatterplot(
    data=plot_df,
    x="adp",
    y="projected_ppg",
    hue="position",
    size="corr_score",
    sizes=(40, 200),
)
for _, r in picks_df.iterrows():
    plt.axvline(r["pick_slot"], color="gray", linestyle="--", alpha=0.4)
plt.gca().invert_xaxis()
plt.xlabel("ADP (lower = earlier)")
plt.ylabel("Projected PPG")
plt.title("ADP vs projection (vertical lines = macker pick slots)")
plt.tight_layout()
plt.show()

# Tier board by blended score
board["tier"] = pd.qcut(board["score_pick1"], q=5, labels=["T5", "T4", "T3", "T2", "T1"])
tier_summary = (
    board.groupby(["tier", "position"], observed=False)
    .agg(players=("player_name", "count"), avg_adp=("adp", "mean"), avg_vorp=("vorp", "mean"))
    .reset_index()
)
display(tier_summary.sort_values(["tier", "position"], ascending=[False, True]))"""
    ),
    md("## 9. Final recommendation table"),
    code(
        """final_rows = []
for _, p in picks_df.iterrows():
    row = board[board["player_name"] == p["player_name"]].iloc[0]
    rationale = []
    if row["position"] == "RB":
        rationale.append("RB depth need")
    if row.get("same_team_stack"):
        rationale.append(f"stack w/ roster QB ({row.get('team', '')})")
    if row["vorp"] > board["vorp"].median():
        rationale.append("above-replacement VORP")
    if row["corr_score"] > board["corr_score"].median():
        rationale.append("positive starter correlation")
    if row["adp"] > p["pick_slot"]:
        rationale.append("ADP value at slot")
    final_rows.append(
        {
            "pick": int(p["pick_slot"]),
            "player": p["player_name"],
            "pos": p["position"],
            "team": p.get("team", ""),
            "adp": round(float(p["adp"]), 1),
            "proj_ppg": round(float(row["projected_ppg"]), 1),
            "vorp": round(float(row["vorp"]), 1),
            "corr_score": round(float(row["corr_score"]), 3),
            "rationale": "; ".join(rationale) or "best blended score",
        }
    )

final_df = pd.DataFrame(final_rows)
display(final_df)"""
    ),
    md(
        """## 10. Top 100 targets (shared engine — same as web app)

The league app's **Draft Help** tab calls the same ``DraftStrategyEngine`` via
``POST /api/leagues/{league_id}/draft-help``. This section reproduces that output."""
    ),
    code(
        """engine_cfg = DraftStrategyConfig(pick_slots=PICK_SLOTS, num_teams=NUM_TEAMS)
engine = DraftStrategyEngine(db, engine_cfg)
league_row = db.get_user_league(LEAGUE_ID, USERNAME)
teams_all = db.get_league_teams(LEAGUE_ID, USERNAME)
my_team_row = next(t for t in teams_all if t["owner_name"] == OWNER_ID)

draft_help = engine.generate(
    league=league_row,
    teams=teams_all,
    my_team_id=my_team_row["team_id"],
    num_players=100,
)

print("Roster needs:")
display(pd.DataFrame(draft_help["roster_needs"]))

print("\\nRecommended picks:")
for p in draft_help["picks"]:
    print(f"  {p['label']}: {p['player']} ({p['position']} {p['team']}) — {'; '.join(p['reasons'])}")

top100 = pd.DataFrame(draft_help["rankings"])
top100["reasons"] = top100["reasons"].apply(lambda rs: "; ".join(rs))
display(
    top100[
        ["rank", "player", "position", "team", "adp", "projected_ppg", "vorp", "correlation", "tier", "reasons"]
    ]
)

print("\\nDraft strategy complete for", USERNAME)
print("League:", LEAGUE_ID, "| picks:", PICK_SLOTS)

db.close()"""
    ),
]

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python (FFPy)",
            "language": "python",
            "name": "ffpy",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    },
    "cells": cells,
}

NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"Wrote {NOTEBOOK_PATH} ({len(cells)} cells)")
