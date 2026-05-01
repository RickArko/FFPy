"""FastAPI + Vue pick'em strategy tester."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ffpy.config import Config
from ffpy.database import FFPyDatabase
from ffpy.pickem_backtest import (
    AllFavorites,
    Backtester,
    ConfidenceBySpread,
    HomeBoost,
    PickStrategy,
    UnderdogTargeted,
    WeekResult,
    WinProbBlend,
)


@dataclass(frozen=True)
class StrategyParamSpec:
    """Frontend-friendly description of a configurable strategy parameter."""

    name: str
    label: str
    kind: Literal["float", "int", "bool", "text"]
    default: Any
    description: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "type": self.kind,
            "default": self.default,
            "description": self.description,
        }
        if self.minimum is not None:
            payload["min"] = self.minimum
        if self.maximum is not None:
            payload["max"] = self.maximum
        if self.step is not None:
            payload["step"] = self.step
        return payload


@dataclass(frozen=True)
class StrategySpec:
    """Registry entry for a supported strategy."""

    name: str
    label: str
    description: str
    strategy_class: type[PickStrategy]
    params: List[StrategyParamSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "params": [param.to_dict() for param in self.params],
        }


STRATEGY_SPECS: Dict[str, StrategySpec] = {
    "AllFavorites": StrategySpec(
        name="AllFavorites",
        label="All Favorites",
        description="Always pick the market favorite in every game.",
        strategy_class=AllFavorites,
    ),
    "ConfidenceBySpread": StrategySpec(
        name="ConfidenceBySpread",
        label="Confidence By Spread",
        description="Pick favorites and rank confidence by absolute spread size.",
        strategy_class=ConfidenceBySpread,
    ),
    "WinProbBlend": StrategySpec(
        name="WinProbBlend",
        label="Win Probability Blend",
        description="Convert adjusted spreads into win probabilities and rank by edge.",
        strategy_class=WinProbBlend,
        params=[
            StrategyParamSpec(
                name="home_advantage",
                label="Home Advantage",
                kind="float",
                default=2.0,
                minimum=-3.0,
                maximum=6.0,
                step=0.5,
                description="Points added to the home spread before converting to win probability.",
            ),
            StrategyParamSpec(
                name="std",
                label="Margin Std Dev",
                kind="float",
                default=13.5,
                minimum=1.0,
                maximum=25.0,
                step=0.5,
                description="Standard deviation for the final-margin model.",
            ),
        ],
    ),
    "HomeBoost": StrategySpec(
        name="HomeBoost",
        label="Home Boost",
        description="Flip close games to the home team and keep favorites elsewhere.",
        strategy_class=HomeBoost,
        params=[
            StrategyParamSpec(
                name="threshold",
                label="Close-Game Threshold",
                kind="float",
                default=3.0,
                minimum=0.0,
                maximum=10.0,
                step=0.5,
                description="Games at or below this spread go to the home team.",
            )
        ],
    ),
    "UnderdogTargeted": StrategySpec(
        name="UnderdogTargeted",
        label="Targeted Underdogs",
        description="Attack close games by flipping the favorite to the underdog.",
        strategy_class=UnderdogTargeted,
        params=[
            StrategyParamSpec(
                name="threshold",
                label="Underdog Threshold",
                kind="float",
                default=3.0,
                minimum=0.0,
                maximum=10.0,
                step=0.5,
                description="Games at or below this spread get switched to the underdog.",
            )
        ],
    ),
}


class StrategySelectionRequest(BaseModel):
    """Strategy selection plus any scalar params."""

    name: str
    params: Dict[str, Any] = Field(default_factory=dict)


class BacktestWindowRequest(BaseModel):
    """Common window options for backtests."""

    season_start: int = Field(ge=2000, le=2100)
    season_end: int = Field(ge=2000, le=2100)
    week_start: int = Field(default=1, ge=1, le=25)
    week_end: int = Field(default=18, ge=1, le=25)
    season_type: str = Field(default="REG", min_length=3, max_length=4)
    require_full_coverage: bool = True


class BacktestRunRequest(BacktestWindowRequest):
    """Request body for a single-strategy run."""

    strategy: StrategySelectionRequest
    persist: bool = False
    note: Optional[str] = None


class BacktestCompareRequest(BacktestWindowRequest):
    """Request body for a multi-strategy leaderboard run."""

    strategies: List[StrategySelectionRequest]


def _coerce_param(kind: str, value: Any, field_name: str) -> Any:
    if kind == "float":
        return float(value)
    if kind == "int":
        return int(value)
    if kind == "bool":
        return bool(value)
    if kind == "text":
        return str(value)
    raise ValueError(f"Unsupported parameter type for {field_name}: {kind}")


def _build_strategy(selection: StrategySelectionRequest) -> PickStrategy:
    spec = STRATEGY_SPECS.get(selection.name)
    if spec is None:
        valid_names = ", ".join(sorted(STRATEGY_SPECS))
        raise ValueError(f"Unknown strategy {selection.name!r}. Choose one of: {valid_names}")

    allowed_params = {param.name: param for param in spec.params}
    unexpected = sorted(set(selection.params) - set(allowed_params))
    if unexpected:
        raise ValueError(
            f"Unexpected params for {selection.name}: {', '.join(unexpected)}"
        )

    params: Dict[str, Any] = {}
    for param in spec.params:
        raw_value = selection.params.get(param.name, param.default)
        params[param.name] = _coerce_param(param.kind, raw_value, param.name)

    return spec.strategy_class(**params)


def _validate_window(request: BacktestWindowRequest) -> None:
    if request.season_start > request.season_end:
        raise HTTPException(status_code=400, detail="season_start must be <= season_end")
    if request.week_start > request.week_end:
        raise HTTPException(status_code=400, detail="week_start must be <= week_end")
    season_type = request.season_type.upper()
    if season_type not in {"REG", "POST", "PRE"}:
        raise HTTPException(status_code=400, detail="season_type must be REG, POST, or PRE")


def _serialize_week_result(result: WeekResult) -> Dict[str, Any]:
    decided = result.correct + result.incorrect
    return {
        "season": result.season,
        "week": result.week,
        "n_games": result.n_games,
        "picks_made": len(result.graded_picks),
        "correct": result.correct,
        "incorrect": result.incorrect,
        "ties": result.ties,
        "win_rate": round(result.correct / decided, 4) if decided > 0 else 0.0,
        "coverage_rate": round(len(result.graded_picks) / result.n_games, 4)
        if result.n_games
        else 0.0,
        "confidence_earned": result.confidence_earned,
        "confidence_max": result.confidence_max,
        "confidence_pct": (
            round(result.confidence_earned / result.confidence_max, 4)
            if result.confidence_max > 0
            else 0.0
        ),
    }


def _frame_records(frame) -> List[Dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def _coverage_payload(db: FFPyDatabase, season_type: str) -> Dict[str, Any]:
    coverage = db.get_data_coverage(season_type=season_type)
    records = _frame_records(coverage)

    seasons = sorted({int(row["season"]) for row in records})
    by_season: List[Dict[str, Any]] = []
    for season in seasons:
        rows = [row for row in records if int(row["season"]) == season]
        weeks = [int(row["week"]) for row in rows]
        fully_usable_weeks = [int(row["week"]) for row in rows if int(row["fully_usable"]) == 1]
        by_season.append(
            {
                "season": season,
                "weeks": weeks,
                "fully_usable_weeks": fully_usable_weeks,
                "max_week": max(weeks) if weeks else None,
            }
        )

    if by_season:
        latest = by_season[-1]
        latest_usable = latest["fully_usable_weeks"] or latest["weeks"]
        default_week_end = max(latest_usable) if latest_usable else 18
        default_window = {
            "season_start": latest["season"],
            "season_end": latest["season"],
            "week_start": 1,
            "week_end": default_week_end,
            "season_type": season_type,
        }
    else:
        default_window = {
            "season_start": Config.NFL_SEASON,
            "season_end": Config.NFL_SEASON,
            "week_start": 1,
            "week_end": 18,
            "season_type": season_type,
        }

    return {
        "rows": records,
        "seasons": seasons,
        "season_summaries": by_season,
        "default_window": default_window,
    }


def create_app(db_path: Optional[str] = None) -> FastAPI:
    """App factory for production use and tests."""

    resolved_db_path = db_path or Config.DATABASE_PATH
    static_dir = Path(__file__).parent / "web" / "pickem_tester"

    app = FastAPI(
        title="FFPy Pick'em Strategy Tester",
        version="0.1.0",
        description="FastAPI backend and Vue frontend for historical NFL pick'em backtests.",
    )
    app.state.db_path = resolved_db_path

    def get_db() -> Iterator[FFPyDatabase]:
        db = FFPyDatabase(db_path=resolved_db_path)
        try:
            yield db
        finally:
            db.close()

    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "database_path": resolved_db_path}

    @app.get("/api/strategies")
    def strategies() -> Dict[str, Any]:
        return {
            "strategies": [
                spec.to_dict()
                for spec in sorted(STRATEGY_SPECS.values(), key=lambda item: item.label)
            ]
        }

    @app.get("/api/coverage")
    def coverage(
        season_type: str = "REG",
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        normalized = season_type.upper()
        if normalized not in {"REG", "POST", "PRE"}:
            raise HTTPException(status_code=400, detail="season_type must be REG, POST, or PRE")
        payload = _coverage_payload(db, normalized)
        payload["season_type"] = normalized
        return payload

    @app.post("/api/backtests/run")
    def run_backtest(
        request: BacktestRunRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        _validate_window(request)
        try:
            strategy = _build_strategy(request.strategy)
            backtester = Backtester(db)
            result = backtester.run(
                strategy,
                season_start=request.season_start,
                season_end=request.season_end,
                week_start=request.week_start,
                week_end=request.week_end,
                season_type=request.season_type.upper(),
                require_full_coverage=request.require_full_coverage,
                persist=request.persist,
                note=request.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        summary = result.to_summary_dict()
        summary["run_id"] = result.run_id

        return {
            "summary": summary,
            "weekly_results": [
                _serialize_week_result(week_result) for week_result in result.weekly_results
            ],
        }

    @app.post("/api/backtests/compare")
    def compare_backtests(
        request: BacktestCompareRequest,
        db: FFPyDatabase = Depends(get_db),
    ) -> Dict[str, Any]:
        _validate_window(request)
        if len(request.strategies) == 0:
            raise HTTPException(status_code=400, detail="Select at least one strategy to compare")

        try:
            strategies = [_build_strategy(strategy) for strategy in request.strategies]
            leaderboard = Backtester(db).compare(
                strategies,
                season_start=request.season_start,
                season_end=request.season_end,
                week_start=request.week_start,
                week_end=request.week_end,
                season_type=request.season_type.upper(),
                require_full_coverage=request.require_full_coverage,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "leaderboard": _frame_records(leaderboard),
            "strategy_count": len(strategies),
        }

    return app


def main() -> None:
    """CLI entry point for the pick'em tester web app."""

    parser = argparse.ArgumentParser(description="Run the FFPy pick'em tester web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    parser.add_argument("--db-path", default=None, help="Optional SQLite database path override.")
    args = parser.parse_args()

    uvicorn.run(create_app(db_path=args.db_path), host=args.host, port=args.port)


__all__ = ["create_app", "main"]


if __name__ == "__main__":
    main()
