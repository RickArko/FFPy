"""FastAPI + Vue pick'em strategy tester."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional

import pandas as pd
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ffpy.auth import (
    AuthenticatedUser,
    TokenVerificationError,
    TokenVerifier,
    build_token_verifier_from_config,
)
from ffpy.config import Config
from ffpy.data import get_positions, get_sample_projections
from ffpy.database import FFPyDatabase
from ffpy.integrations import ESPNIntegration, SportsDataIntegration
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
from ffpy.projections import HistoricalProjectionModel
from ffpy.repositories.base import HistoricalGamesRepository
from ffpy.repositories.sqlite_games import SQLiteHistoricalGamesRepository
from ffpy.usage_logging import (
    NoopUsageEventLogger,
    SQLiteUsageEventLogger,
    UsageEvent,
    UsageEventLogger,
    encode_strategy_names,
    hash_identifier,
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

PROJECTION_SOURCE_LABELS = {
    "historical": "Historical Model",
    "api": "API Data",
    "sample": "Sample Data",
}

logger = logging.getLogger(__name__)


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
        raise ValueError(f"Unexpected params for {selection.name}: {', '.join(unexpected)}")

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
        "coverage_rate": round(len(result.graded_picks) / result.n_games, 4) if result.n_games else 0.0,
        "confidence_earned": result.confidence_earned,
        "confidence_max": result.confidence_max,
        "confidence_pct": (
            round(result.confidence_earned / result.confidence_max, 4) if result.confidence_max > 0 else 0.0
        ),
    }


def _frame_records(frame) -> List[Dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def _normalize_projection_frame(frame: pd.DataFrame, week: int) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "player",
                "team",
                "position",
                "opponent",
                "projected_points",
                "week",
            ]
        )

    normalized = frame.copy()
    for column, default in {
        "player": "",
        "team": "",
        "position": "",
        "opponent": "TBD",
        "projected_points": 0.0,
        "week": week,
    }.items():
        if column not in normalized.columns:
            normalized[column] = default

    normalized["projected_points"] = pd.to_numeric(normalized["projected_points"], errors="coerce").fillna(
        0.0
    )
    normalized["week"] = pd.to_numeric(normalized["week"], errors="coerce").fillna(week).astype(int)
    normalized["position"] = normalized["position"].astype(str).str.upper()
    return normalized.sort_values(["projected_points", "player"], ascending=[False, True])


def _load_historical_projection_frame(week: int, db_path: str) -> pd.DataFrame:
    db = FFPyDatabase(db_path=db_path)
    try:
        model = HistoricalProjectionModel(db=db)
        return model.generate_projections(
            season=Config.NFL_SEASON,
            week=week,
            lookback_weeks=4,
            recent_weight=0.6,
        )
    finally:
        db.close()


def _load_api_projection_frame(week: int) -> pd.DataFrame:
    api_provider = Config.get_api_provider()

    if api_provider == "sportsdata" and Config.is_sportsdata_configured():
        sportsdata = SportsDataIntegration(api_key=Config.SPORTSDATA_API_KEY)
        if sportsdata.is_available():
            frame = sportsdata.get_projections(week=week, season=Config.NFL_SEASON)
            if not frame.empty:
                return frame

    return ESPNIntegration().get_projections(week=week, season=Config.NFL_SEASON)


def _projection_source_frame(
    source: str, week: int, db_path: str
) -> tuple[pd.DataFrame, str, bool, Optional[str]]:
    fallback_used = False
    message = None

    if source == "sample":
        frame = get_sample_projections(week)
    elif source == "historical":
        try:
            frame = _load_historical_projection_frame(week, db_path)
        except Exception:
            frame = pd.DataFrame()
            message = "Historical model could not read projection inputs; sample projections are shown."
        if frame.empty:
            fallback_used = True
            message = (
                message or "Historical projections are empty for this week; sample projections are shown."
            )
            frame = get_sample_projections(week)
    elif source == "api":
        try:
            frame = _load_api_projection_frame(week)
        except Exception:
            frame = pd.DataFrame()
            message = "Projection API could not return usable data; sample projections are shown."
        if frame.empty:
            fallback_used = True
            message = message or "Projection API returned no data; sample projections are shown."
            frame = get_sample_projections(week)
    else:
        valid_sources = ", ".join(sorted(PROJECTION_SOURCE_LABELS))
        raise HTTPException(status_code=400, detail=f"source must be one of: {valid_sources}")

    return _normalize_projection_frame(frame, week), source, fallback_used, message


def _projection_summary(frame: pd.DataFrame) -> Dict[str, Any]:
    if frame.empty:
        return {
            "total_players": 0,
            "average_projected_points": 0.0,
            "median_projected_points": 0.0,
            "top_player": None,
            "top_projection": 0.0,
        }

    top_row = frame.iloc[0]
    return {
        "total_players": int(len(frame)),
        "average_projected_points": round(float(frame["projected_points"].mean()), 2),
        "median_projected_points": round(float(frame["projected_points"].median()), 2),
        "top_player": top_row["player"],
        "top_projection": round(float(top_row["projected_points"]), 2),
    }


def _projection_position_totals(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    for position in get_positions():
        position_frame = frame[frame["position"] == position]
        rows.append(
            {
                "position": position,
                "players": int(len(position_frame)),
                "average_projected_points": (
                    round(float(position_frame["projected_points"].mean()), 2)
                    if not position_frame.empty
                    else 0.0
                ),
                "top_projection": (
                    round(float(position_frame["projected_points"].max()), 2)
                    if not position_frame.empty
                    else 0.0
                ),
            }
        )
    return rows


def _projection_breakdown(frame: pd.DataFrame, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    return {
        position: _frame_records(frame[frame["position"] == position].head(limit))
        for position in get_positions()
    }


def _coverage_payload(repository: HistoricalGamesRepository, season_type: str) -> Dict[str, Any]:
    coverage = repository.get_data_coverage(season_type=season_type)
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


def _estimate_cost_units(
    *,
    season_start: int,
    season_end: int,
    week_start: int,
    week_end: int,
    strategy_count: int,
) -> int:
    seasons = (season_end - season_start) + 1
    weeks = (week_end - week_start) + 1
    return max(1, seasons * weeks * strategy_count)


def _public_auth_config(auth_enabled: bool) -> Dict[str, Any]:
    browser_auth_available = bool(auth_enabled and Config.SUPABASE_URL and Config.SUPABASE_BROWSER_KEY)
    return {
        "auth_required": auth_enabled,
        "browser_auth_available": browser_auth_available,
        "supabase_url": Config.SUPABASE_URL if browser_auth_available else None,
        "supabase_anon_key": Config.SUPABASE_BROWSER_KEY if browser_auth_available else None,
        "public_app_url": Config.PUBLIC_APP_URL,
    }


def create_app(
    db_path: Optional[str] = None,
    *,
    require_auth: Optional[bool] = None,
    auth_verifier: Optional[TokenVerifier] = None,
    usage_logger: Optional[UsageEventLogger] = None,
) -> FastAPI:
    """App factory for production use and tests."""

    resolved_db_path = db_path or Config.DATABASE_PATH
    static_dir = Path(__file__).parent / "web" / "pickem_tester"
    auth_enabled = Config.WEB_AUTH_ENABLED if require_auth is None else require_auth
    resolved_auth_verifier = auth_verifier or build_token_verifier_from_config()
    if auth_enabled and resolved_auth_verifier is None:
        raise ValueError("Auth is enabled but no token verifier is configured")
    resolved_usage_logger = usage_logger or (
        SQLiteUsageEventLogger(resolved_db_path) if resolved_db_path else NoopUsageEventLogger()
    )
    bearer = HTTPBearer(auto_error=False)

    app = FastAPI(
        title="FFPy Pick'em Strategy Tester",
        version="0.1.0",
        description="FastAPI backend and Vue frontend for historical NFL pick'em backtests.",
    )
    app.state.db_path = resolved_db_path
    app.state.auth_enabled = auth_enabled
    favicon_path = static_dir / "favicon.ico"

    def get_repository() -> Iterator[SQLiteHistoricalGamesRepository]:
        db = FFPyDatabase(db_path=resolved_db_path)
        repository = SQLiteHistoricalGamesRepository(db)
        try:
            yield repository
        finally:
            repository.close()

    def _build_usage_event(
        *,
        request: Request,
        route: str,
        event_type: str,
        success: bool,
        strategy_names: List[str],
        cost_units: int,
        user: Optional[AuthenticatedUser] = None,
        denied_reason: Optional[str] = None,
    ) -> UsageEvent:
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        return UsageEvent(
            route=route,
            event_type=event_type,
            success=success,
            user_id=user.user_id if user else None,
            email=user.email if user else None,
            denied_reason=denied_reason,
            strategy_names_json=encode_strategy_names(strategy_names),
            cost_units=cost_units,
            ip_hash=hash_identifier(client_ip),
            user_agent_hash=hash_identifier(user_agent),
            request_fingerprint=hash_identifier(
                f"{client_ip}:{user_agent}:{route}:{encode_strategy_names(strategy_names)}"
            ),
        )

    def _log_event(event: UsageEvent) -> None:
        resolved_usage_logger.log_event(event)

    def _require_verified_user(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials],
        *,
        route: str,
        event_type: str,
        strategy_names: List[str],
        cost_units: int,
    ) -> Optional[AuthenticatedUser]:
        if not auth_enabled:
            return None

        if credentials is None:
            _log_event(
                _build_usage_event(
                    request=request,
                    route=route,
                    event_type=event_type,
                    success=False,
                    strategy_names=strategy_names,
                    cost_units=cost_units,
                    denied_reason="missing_bearer_token",
                )
            )
            raise HTTPException(status_code=401, detail="Authentication required")

        assert resolved_auth_verifier is not None
        try:
            user = resolved_auth_verifier.verify_access_token(credentials.credentials)
        except TokenVerificationError as exc:
            _log_event(
                _build_usage_event(
                    request=request,
                    route=route,
                    event_type=event_type,
                    success=False,
                    strategy_names=strategy_names,
                    cost_units=cost_units,
                    denied_reason="invalid_bearer_token",
                )
            )
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        if not user.email_confirmed:
            _log_event(
                _build_usage_event(
                    request=request,
                    route=route,
                    event_type=event_type,
                    success=False,
                    strategy_names=strategy_names,
                    cost_units=cost_units,
                    user=user,
                    denied_reason="email_not_verified",
                )
            )
            raise HTTPException(status_code=403, detail="Verified email required")

        return user

    def _get_current_user(
        credentials: Optional[HTTPAuthorizationCredentials],
    ) -> Optional[AuthenticatedUser]:
        if credentials is None or resolved_auth_verifier is None:
            return None
        try:
            return resolved_auth_verifier.verify_access_token(credentials.credentials)
        except TokenVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/projections", include_in_schema=False)
    def projections_frontend() -> FileResponse:
        return FileResponse(static_dir / "projections.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(favicon_path)

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "database_path": resolved_db_path,
            "auth_required": auth_enabled,
        }

    @app.get("/api/auth/me")
    def auth_me(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> Dict[str, Any]:
        user = _get_current_user(credentials)
        return {
            "authenticated": user is not None,
            "auth_required": auth_enabled,
            "user": user.to_dict() if user else None,
        }

    @app.get("/api/auth/config")
    def auth_config() -> Dict[str, Any]:
        return _public_auth_config(auth_enabled)

    @app.get("/api/strategies")
    def strategies() -> Dict[str, Any]:
        return {
            "strategies": [
                spec.to_dict() for spec in sorted(STRATEGY_SPECS.values(), key=lambda item: item.label)
            ]
        }

    @app.get("/api/coverage")
    def coverage(
        season_type: str = "REG",
        repository: SQLiteHistoricalGamesRepository = Depends(get_repository),
    ) -> Dict[str, Any]:
        normalized = season_type.upper()
        if normalized not in {"REG", "POST", "PRE"}:
            raise HTTPException(status_code=400, detail="season_type must be REG, POST, or PRE")
        payload = _coverage_payload(repository, normalized)
        payload["season_type"] = normalized
        return payload

    @app.get("/api/projections")
    def projections(
        week: int = Query(default=1, ge=1, le=18),
        source: Literal["historical", "api", "sample"] = "historical",
        position: str = "ALL",
        top_n: int = Query(default=25, ge=1, le=200),
    ) -> Dict[str, Any]:
        normalized_position = position.upper()
        valid_positions = get_positions()
        if normalized_position not in {"ALL", *valid_positions}:
            raise HTTPException(
                status_code=400,
                detail=f"position must be ALL or one of: {', '.join(valid_positions)}",
            )

        frame, source_used, fallback_used, message = _projection_source_frame(source, week, resolved_db_path)
        filtered = frame if normalized_position == "ALL" else frame[frame["position"] == normalized_position]
        filtered = filtered.head(top_n)

        return {
            "season": Config.NFL_SEASON,
            "week": week,
            "source": source_used,
            "source_label": PROJECTION_SOURCE_LABELS[source_used],
            "fallback_used": fallback_used,
            "message": message,
            "position": normalized_position,
            "positions": valid_positions,
            "summary": _projection_summary(filtered),
            "position_totals": _projection_position_totals(frame),
            "position_breakdown": _projection_breakdown(frame),
            "players": _frame_records(filtered),
        }

    @app.post("/api/backtests/run")
    def run_backtest(
        http_request: Request,
        request: BacktestRunRequest,
        repository: SQLiteHistoricalGamesRepository = Depends(get_repository),
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> Dict[str, Any]:
        _validate_window(request)
        strategy_names = [request.strategy.name]
        cost_units = _estimate_cost_units(
            season_start=request.season_start,
            season_end=request.season_end,
            week_start=request.week_start,
            week_end=request.week_end,
            strategy_count=1,
        )
        current_user = _require_verified_user(
            http_request,
            credentials,
            route="/api/backtests/run",
            event_type="backtest_run",
            strategy_names=strategy_names,
            cost_units=cost_units,
        )
        try:
            strategy = _build_strategy(request.strategy)
            backtester = Backtester(repository)
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

        _log_event(
            _build_usage_event(
                request=http_request,
                route="/api/backtests/run",
                event_type="backtest_run",
                success=True,
                strategy_names=strategy_names,
                cost_units=cost_units,
                user=current_user,
            )
        )

        return {
            "summary": summary,
            "weekly_results": [_serialize_week_result(week_result) for week_result in result.weekly_results],
        }

    @app.post("/api/backtests/compare")
    def compare_backtests(
        http_request: Request,
        request: BacktestCompareRequest,
        repository: SQLiteHistoricalGamesRepository = Depends(get_repository),
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> Dict[str, Any]:
        _validate_window(request)
        if len(request.strategies) == 0:
            raise HTTPException(status_code=400, detail="Select at least one strategy to compare")

        strategy_names = [strategy.name for strategy in request.strategies]
        cost_units = _estimate_cost_units(
            season_start=request.season_start,
            season_end=request.season_end,
            week_start=request.week_start,
            week_end=request.week_end,
            strategy_count=len(request.strategies),
        )
        current_user = _require_verified_user(
            http_request,
            credentials,
            route="/api/backtests/compare",
            event_type="backtest_compare",
            strategy_names=strategy_names,
            cost_units=cost_units,
        )
        try:
            strategies = [_build_strategy(strategy) for strategy in request.strategies]
            leaderboard = Backtester(repository).compare(
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

        _log_event(
            _build_usage_event(
                request=http_request,
                route="/api/backtests/compare",
                event_type="backtest_compare",
                success=True,
                strategy_names=strategy_names,
                cost_units=cost_units,
                user=current_user,
            )
        )

        return {
            "leaderboard": _frame_records(leaderboard),
            "strategy_count": len(strategies),
        }

    return app


def main() -> None:
    """CLI entry point for the pick'em tester web app."""

    parser = argparse.ArgumentParser(description="Run the FFPy pick'em tester web app.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to listen on.")
    parser.add_argument("--db-path", default=None, help="Optional SQLite database path override.")
    args = parser.parse_args()

    app = create_app(db_path=args.db_path)
    logger.info(
        "Starting pick'em web app on %s:%s with database=%s auth_enabled=%s",
        args.host,
        args.port,
        app.state.db_path,
        app.state.auth_enabled,
    )
    uvicorn.run(app, host=args.host, port=args.port)


__all__ = ["create_app", "main"]


if __name__ == "__main__":
    main()
