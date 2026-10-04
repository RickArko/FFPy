"""CBS Sports fantasy football league client.

League routes on ``https://api.cbssports.com/fantasy`` require a member
``access_token``. Public ``/players/list`` does not. This module does not log
the token and does not store a CBS password.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

CBS_API_BASE = "https://api.cbssports.com/fantasy"
_PLAYER_CACHE_TTL = 6 * 60 * 60
_PLAYER_CACHE: dict[str, Any] = {"data": None, "fetched_at": 0.0}

# CBS abbrs read by the ffmwr position map. FLEX on CBS is superflex.
_STARTER_SLOTS = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "K": "K",
    "DST": "DST",
    "D": "DST",
    "DEF": "DST",
    "D/ST": "DST",
    "RB-WR": "FLEX",
    "WR-TE": "FLEX",
    "RB-WR-TE": "FLEX",
    "FLEX": "OP",
    "OP": "OP",
    "SUPERFLEX": "OP",
}
_IDP_ABBRS = frozenset({"DL", "LB", "DB", "DE", "DT", "CB", "S", "DL-LB-DB"})
_TAXI_ABBRS = frozenset({"TX", "TAXI", "TAX"})
_BENCH_ABBRS = frozenset({"RS", "BN", "BE"})
_IR_ABBRS = frozenset({"I", "IR"})

# Normalized (lowercase, alphanumerics only) CBS scoring abbrs → Sleeper keys.
_SCORING_ABBRS = {
    "payds": "pass_yd",
    "passingyards": "pass_yd",
    "py": "pass_yd",
    "passyd": "pass_yd",
    "patd": "pass_td",
    "passingtouchdowns": "pass_td",
    "ptd": "pass_td",
    "passtd": "pass_td",
    "int": "pass_int",
    "interceptions": "pass_int",
    "passint": "pass_int",
    "ruyds": "rush_yd",
    "rushingyards": "rush_yd",
    "rushyd": "rush_yd",
    "rutd": "rush_td",
    "rushingtouchdowns": "rush_td",
    "rushtd": "rush_td",
    "rec": "rec",
    "receptions": "rec",
    "reyds": "rec_yd",
    "receivingyards": "rec_yd",
    "recyd": "rec_yd",
    "retd": "rec_td",
    "receivingtouchdowns": "rec_td",
    "rectd": "rec_td",
    "fuml": "fum_lost",
    "fumbleslost": "fum_lost",
    "fumlost": "fum_lost",
}

_LEAGUE_HOST = re.compile(r"https?://([a-z0-9-]+)\.football\.cbssports\.com", re.IGNORECASE)
_LEAGUE_QUERY = re.compile(r"[?&]league_id=([A-Za-z0-9-]+)", re.IGNORECASE)
_LEAGUE_PATH = re.compile(r"/leagues/([A-Za-z0-9-]+)", re.IGNORECASE)
_BARE_ID = re.compile(r"^[A-Za-z0-9-]+$")
_TOKEN_IN_URL = re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE)


class CBSAuthError(Exception):
    """CBS rejected the access token."""


class CBSAPIError(Exception):
    """CBS returned a non-auth failure."""


def redact_cbs_secret(text: str) -> str:
    """Drop access tokens from text that might be logged or returned."""

    return _TOKEN_IN_URL.sub(r"\1REDACTED", text or "")


def parse_cbs_league_id(raw: str) -> str:
    """Pull a CBS league id out of a league URL or a bare id."""

    text = (raw or "").strip()
    if not text:
        raise ValueError("empty league id")
    host = _LEAGUE_HOST.search(text)
    if host and host.group(1).lower() not in {"www", "api"}:
        return host.group(1)
    query = _LEAGUE_QUERY.search(text)
    if query:
        return query.group(1)
    path = _LEAGUE_PATH.search(text)
    if path:
        return path.group(1)
    if _BARE_ID.fullmatch(text):
        return text
    raise ValueError("unrecognized CBS league link")


def _as_list(value: Any) -> list[dict]:
    """Normalize a CBS node that may be a list, one object, or an XML-style wrapper."""

    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("team", "player", "category", "period", "matchup"):
            if key in value:
                return _as_list(value[key])
        return [value]
    return []


def _nested(payload: dict, *keys: str) -> Any:
    node: Any = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _first_int(value: Any) -> Optional[int]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else None


def _optional_score(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _norm_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


class CBSLeagueClient:
    """HTTP client for the CBS fantasy v3 JSON API."""

    def __init__(self, access_token: str, *, session: Any = None, timeout: float = 30.0):
        token = (access_token or "").strip()
        if not token:
            raise CBSAuthError("CBS access token is empty")
        self.access_token = token
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(self, path: str, **params: Any) -> dict:
        """GET one fantasy resource. ``path`` starts with ``/``."""

        query = {
            "version": "3.0",
            "response_format": "json",
            "sport": "football",
            "access_token": self.access_token,
        }
        query.update({key: value for key, value in params.items() if value is not None})
        url = f"{CBS_API_BASE}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": self.access_token,
            "User-Agent": "sleeper-brain/cbs",
        }
        try:
            response = self.session.get(url, params=query, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise CBSAPIError("CBS request failed") from exc
        return _parse_response(response)

    def player_catalog(self) -> dict[str, dict]:
        """Map CBS player id → public player row, cached on disk for six hours."""

        cached = _load_player_cache()
        if cached is not None:
            return cached
        payload = self.fetch("/players/list")
        players = _as_list(_nested(payload, "body", "players"))
        catalog = {str(player.get("id")): player for player in players if player.get("id") is not None}
        _save_player_cache(catalog)
        return catalog


def _parse_response(response: Any) -> dict:
    status = int(getattr(response, "status_code", 0) or 0)
    text = redact_cbs_secret(getattr(response, "text", "") or "")
    lowered = text.lower()
    if status in (401, 403) or "failed authentication" in lowered or "invalid access token" in lowered:
        raise CBSAuthError("CBS rejected the access token")
    if status >= 400:
        raise CBSAPIError(f"CBS HTTP {status}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CBSAPIError("CBS returned a non-JSON body") from exc
    if not isinstance(payload, dict):
        raise CBSAPIError("CBS returned an unexpected payload")
    code = payload.get("statusCode")
    if code is not None and int(code) != 200:
        message = str(_nested(payload, "body", "msg") or payload.get("statusMessage") or "")
        if "auth" in message.lower() or "token" in message.lower():
            raise CBSAuthError("CBS rejected the access token")
        raise CBSAPIError(f"CBS status {code}")
    return payload


def _player_cache_path() -> Path:
    from ffpy.config import Config

    cache_dir = Path(Config.DATABASE_PATH).expanduser().parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cbs_players_football.json"


def _load_player_cache() -> Optional[dict[str, dict]]:
    now = time.time()
    cached = _PLAYER_CACHE.get("data")
    if isinstance(cached, dict) and (now - float(_PLAYER_CACHE.get("fetched_at") or 0)) < _PLAYER_CACHE_TTL:
        return cached
    path = _player_cache_path()
    if not path.exists():
        return None
    if now - path.stat().st_mtime >= _PLAYER_CACHE_TTL:
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return None
    _PLAYER_CACHE["data"] = data
    _PLAYER_CACHE["fetched_at"] = now
    return data


def _save_player_cache(catalog: dict[str, dict]) -> None:
    path = _player_cache_path()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(catalog, handle)
    _PLAYER_CACHE["data"] = catalog
    _PLAYER_CACHE["fetched_at"] = time.time()


def _taxi_abbrs(rules_payload: dict) -> set[str]:
    abbrs = set(_TAXI_ABBRS)
    statuses = _as_list(_nested(rules_payload, "body", "rules", "roster", "statuses"))
    for status in statuses:
        description = str(status.get("description") or "").lower()
        abbr = str(status.get("abbr") or "").upper()
        if "taxi" in description and abbr:
            abbrs.add(abbr)
    return abbrs


def _roster_positions(rules_payload: dict) -> tuple[list[str], list[str]]:
    """Return ``(starter slots, idp slots)``. Bench, IR, and taxi are omitted."""

    starters: list[str] = []
    idp: list[str] = []
    positions = _as_list(_nested(rules_payload, "body", "rules", "roster", "positions"))
    for position in positions:
        abbr = str(position.get("abbr") or "").upper()
        try:
            count = int(position.get("max_active") or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0 or not abbr:
            continue
        if abbr in _IDP_ABBRS:
            idp.extend([abbr] * count)
            continue
        mapped = _STARTER_SLOTS.get(abbr)
        if mapped is None or mapped in {"BN", "IR", "TAX"}:
            continue
        starters.extend([mapped] * count)
    return starters, idp


def _scoring_settings(payload: dict) -> dict[str, float]:
    rows = _as_list(_nested(payload, "body", "scoring_categories"))
    settings: dict[str, float] = {}
    for row in rows:
        mapped = _SCORING_ABBRS.get(_norm_key(row.get("abbr"))) or _SCORING_ABBRS.get(
            _norm_key(row.get("name"))
        )
        if not mapped or mapped in settings:
            continue
        raw = row.get("points", row.get("value"))
        try:
            settings[mapped] = float(raw)
        except (TypeError, ValueError):
            continue
    return settings


def _display_name(player: dict, catalog: dict[str, dict]) -> str:
    position = str(player.get("position") or "").upper()
    pro_team = str(player.get("pro_team") or "").strip()
    if position in {"DST", "D", "DEF", "D/ST"} and pro_team:
        return f"{pro_team} DST"
    name = str(player.get("fullname") or "").strip()
    if not name:
        name = f"{player.get('firstname') or ''} {player.get('lastname') or ''}".strip()
    if not name:
        cached = catalog.get(str(player.get("id") or ""))
        if isinstance(cached, dict):
            name = str(cached.get("fullname") or "").strip()
            if str(cached.get("position") or "").upper() == "DST" and cached.get("pro_team"):
                return f"{cached.get('pro_team')} DST"
    return " ".join(name.split())


def _lineup_slot(player: dict, taxi_abbrs: set[str]) -> str:
    status = str(player.get("roster_status") or "").upper()
    slot = str(player.get("roster_pos") or "").upper()
    if status in taxi_abbrs or slot in taxi_abbrs:
        return "TAX"
    if status in _IR_ABBRS or slot in _IR_ABBRS:
        return "IR"
    if status in _BENCH_ABBRS or slot in _BENCH_ABBRS:
        return "BN"
    mapped = _STARTER_SLOTS.get(slot) or _STARTER_SLOTS.get(status)
    if mapped:
        return mapped
    if slot:
        return slot
    return "BN"


def _player_row(player: dict, catalog: dict[str, dict], taxi_abbrs: set[str]) -> Optional[dict]:
    name = _display_name(player, catalog)
    if not name:
        return None
    position = str(player.get("position") or "").upper()
    if position in {"D", "DEF", "D/ST", "DST"}:
        position = "DST"
    row: dict[str, Any] = {
        "player": name,
        "position": position or "?",
        "team": str(player.get("pro_team") or ""),
        "lineup_slot": _lineup_slot(player, taxi_abbrs),
        "cbs_player_id": str(player.get("id") or ""),
    }
    elias = player.get("elias_id")
    if elias:
        row["elias_id"] = str(elias)
    contract = None
    wildcards = player.get("wildcards")
    if isinstance(wildcards, dict) and wildcards.get("contract") not in (None, "", 0, "0"):
        contract = wildcards.get("contract")
    elif player.get("contract") not in (None, "", 0, "0"):
        contract = player.get("contract")
    if contract is not None:
        row["contract"] = str(contract)
        row["roster_source"] = "keeper"
    return row


def _standings_index(payload: Optional[dict]) -> dict[str, dict]:
    if not payload:
        return {}
    body = payload.get("body") if isinstance(payload, dict) else None
    standings = body.get("overall_standings") if isinstance(body, dict) else None
    if isinstance(standings, dict) and isinstance(standings.get("divisions"), list):
        rows: list[dict] = []
        for division in standings["divisions"]:
            if isinstance(division, dict):
                rows.extend(_as_list(division.get("teams")))
    else:
        rows = _as_list(_nested(payload, "body", "overall_standings", "teams"))
        if not rows:
            rows = _as_list(standings)
    return {str(row.get("id")): row for row in rows if row.get("id") is not None}


def _matchups(league_id: str, season: int, payload: dict) -> list[dict]:
    periods = _as_list(_nested(payload, "body", "schedule", "periods"))
    ordered = sorted(periods, key=lambda period: _first_int(period.get("label")) or 0)
    matchups: list[dict] = []
    for period in ordered:
        games = _as_list(period.get("matchups"))
        if not games:
            break
        week = _first_int(period.get("label"))
        if week is None:
            continue
        for game in games:
            home = game.get("home_team") if isinstance(game.get("home_team"), dict) else {}
            away = game.get("away_team") if isinstance(game.get("away_team"), dict) else {}
            home_id = home.get("id")
            away_id = away.get("id")
            if home_id is None or away_id is None:
                continue
            matchups.append(
                {
                    "week": week,
                    "home_team_id": f"cbs:{league_id}:{season}:{home_id}",
                    "away_team_id": f"cbs:{league_id}:{season}:{away_id}",
                    "home_score": _optional_score(home.get("points")),
                    "away_score": _optional_score(away.get("points")),
                    "is_playoff": 0,
                    "is_consolation": 0,
                }
            )
    return matchups


def _optional(client: CBSLeagueClient, path: str, **params: Any) -> Optional[dict]:
    try:
        return client.fetch(path, **params)
    except CBSAuthError:
        raise
    except CBSAPIError:
        logger.info("CBS resource %s unavailable; continuing without it", path)
        return None


def build_cbs_import(
    league_id: str,
    season: int,
    creds: dict,
    *,
    client: Optional[CBSLeagueClient] = None,
) -> dict:
    """Fetch a CBS league and return the ``store_user_league`` payload."""

    from ffpy.sleeper_import import scoring_type_from_sleeper

    native = parse_cbs_league_id(str(league_id))
    cbs = client or CBSLeagueClient(str(creds.get("access_token") or ""))
    details = cbs.fetch("/league/details", league_id=native)
    teams_payload = cbs.fetch("/league/teams", league_id=native)
    rosters_payload = cbs.fetch("/league/rosters", league_id=native, team_id="all")
    rules_payload = _optional(cbs, "/league/rules", league_id=native) or {}
    scoring_payload = _optional(cbs, "/league/scoring/categories", league_id=native) or {}
    schedule_payload = _optional(cbs, "/league/schedules", league_id=native, period="all") or {}
    standings_payload = _optional(cbs, "/league/standings/overall", league_id=native)

    info = _nested(details, "body", "league_details") or {}
    if not isinstance(info, dict):
        info = {}
    taxi = _taxi_abbrs(rules_payload)
    roster_positions, idp_positions = _roster_positions(rules_payload)
    scoring_settings = _scoring_settings(scoring_payload)
    standings = _standings_index(standings_payload)

    needs_catalog = False
    roster_teams = _as_list(_nested(rosters_payload, "body", "rosters", "teams"))
    for team in roster_teams:
        for player in _as_list(team.get("players")):
            if (
                not str(player.get("fullname") or "").strip()
                and not str(player.get("pro_team") or "").strip()
            ):
                needs_catalog = True
                break
    catalog = cbs.player_catalog() if needs_catalog else {}

    rosters_by_team: dict[str, list[dict]] = {}
    for team in roster_teams:
        team_id = str(team.get("id") or "")
        rows = []
        for player in _as_list(team.get("players")):
            row = _player_row(player, catalog, taxi)
            if row:
                rows.append(row)
        rosters_by_team[team_id] = rows

    team_list = []
    for team in _as_list(_nested(teams_payload, "body", "teams")):
        team_id = str(team.get("id") or "")
        owners = _as_list(team.get("owners"))
        owner = str(owners[0].get("name") or "Unknown") if owners else "Unknown"
        standing = standings.get(team_id, {})
        team_list.append(
            {
                "team_id": f"cbs:{native}:{season}:{team_id}",
                "name": team.get("name") or "Unknown",
                "owner": owner,
                "wins": int(_float_or_zero(standing.get("wins"))),
                "losses": int(_float_or_zero(standing.get("losses"))),
                "ties": int(_float_or_zero(standing.get("ties"))),
                "points_for": _float_or_zero(standing.get("points_scored")),
                "points_against": _float_or_zero(standing.get("points_against")),
                "rank": _first_int(standing.get("order")),
                "roster": rosters_by_team.get(team_id, []),
            }
        )

    playoff = _nested(rules_payload, "body", "rules", "schedule", "num_playoff_teams", "value")
    try:
        num_teams = int(info.get("num_teams") or len(team_list) or 0)
    except (TypeError, ValueError):
        num_teams = len(team_list)

    return {
        "league": {
            "league_id": f"cbs:{native}:{season}",
            "provider": "cbs",
            "name": info.get("name") or "CBS league",
            "season": season,
            "sleeper_league_id": native,
            "scoring_type": scoring_type_from_sleeper(scoring_settings),
            "scoring_settings": scoring_settings,
            "roster_positions": roster_positions,
            "idp_positions": idp_positions,
            "roster_size": None,
            "num_teams": num_teams,
            "playoff_teams": _first_int(playoff),
        },
        "teams": team_list,
        "matchups": _matchups(native, season, schedule_payload),
    }
