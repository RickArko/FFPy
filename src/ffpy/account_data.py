"""User-scoped data export, purge, and feature-artifact helpers (GDPR)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ffpy.database import FFPyDatabase

ARTIFACT_TTL_DAYS = 90
ARTIFACT_CAP_PER_FEATURE = 20

_USER_SCOPED_TABLES = (
    "user_feature_artifacts",
    "user_leagues",
    "league_franchises",
    "user_sleeper_profiles",
    "user_credentials",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _table_exists(db: FFPyDatabase, table: str) -> bool:
    row = db.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _row_to_jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (bytes, bytearray)):
            out[key] = value.decode("utf-8", errors="replace")
        else:
            out[key] = value
    return out


def export_user_data(
    db: FFPyDatabase,
    user_id: str,
    *,
    email: str | None = None,
) -> dict[str, Any]:
    """Build a portable JSON package of all user-scoped app data."""

    profile = db.get_sleeper_profile(user_id)
    franchises = db.list_franchises(user_id)
    # Flatten franchise nesting for export; seasons are included by list_franchises.
    franchise_rows = [_row_to_jsonable({k: v for k, v in f.items() if k != "seasons"}) for f in franchises]
    for dest, src in zip(franchise_rows, franchises):
        dest["seasons"] = [_row_to_jsonable(s) for s in src.get("seasons", [])]

    leagues_out: list[dict[str, Any]] = []
    for league in db.get_user_leagues(user_id):
        league_id = league["league_id"]
        teams = db.get_teams_for_league(league_id)
        matchups = db.conn.execute(
            "SELECT * FROM league_matchups WHERE league_id = ? ORDER BY week, matchup_id",
            (league_id,),
        ).fetchall()
        leagues_out.append(
            {
                "league": _row_to_jsonable(dict(league)),
                "teams": [_row_to_jsonable(dict(t)) for t in teams],
                "matchups": [_row_to_jsonable(dict(m)) for m in matchups],
            }
        )

    artifacts: list[dict[str, Any]] = []
    if _table_exists(db, "user_feature_artifacts"):
        artifacts = list_feature_artifacts(db, user_id, include_expired=True)

    return {
        "exported_at": _iso(_utcnow()),
        "user": {"user_id": user_id, "email": email},
        "sleeper_profile": _row_to_jsonable(profile) if profile else None,
        "franchises": franchise_rows,
        "leagues": leagues_out,
        "feature_artifacts": artifacts,
    }


def purge_user_data(db: FFPyDatabase, user_id: str) -> dict[str, int]:
    """Hard-delete all user-scoped rows for ``user_id``. Returns delete counts."""

    counts: dict[str, int] = {}

    if _table_exists(db, "user_feature_artifacts"):
        cur = db.conn.execute("DELETE FROM user_feature_artifacts WHERE user_id = ?", (user_id,))
        counts["feature_artifacts"] = cur.rowcount

    # Leagues owned directly; teams/matchups cascade via FK.
    cur = db.conn.execute("DELETE FROM user_leagues WHERE user_id = ?", (user_id,))
    counts["leagues"] = cur.rowcount

    cur = db.conn.execute("DELETE FROM league_franchises WHERE user_id = ?", (user_id,))
    counts["franchises"] = cur.rowcount

    cur = db.conn.execute("DELETE FROM user_sleeper_profiles WHERE user_id = ?", (user_id,))
    counts["sleeper_profiles"] = cur.rowcount

    if _table_exists(db, "user_credentials"):
        cur = db.conn.execute("DELETE FROM user_credentials WHERE user_id = ?", (user_id,))
        counts["credentials"] = cur.rowcount

    db.conn.commit()
    return counts


def save_feature_artifact(
    db: FFPyDatabase,
    user_id: str,
    *,
    feature: str,
    request: dict[str, Any] | list[Any] | str,
    result: dict[str, Any] | list[Any] | str,
    league_id: str | None = None,
    title: str | None = None,
    ttl_days: int = ARTIFACT_TTL_DAYS,
    cap: int = ARTIFACT_CAP_PER_FEATURE,
) -> dict[str, Any]:
    """Insert a feature artifact and enforce per-feature cap (oldest first)."""

    if not feature.strip():
        raise ValueError("feature is required")
    if cap < 1:
        raise ValueError("cap must be >= 1")
    if not _table_exists(db, "user_feature_artifacts"):
        raise RuntimeError("user_feature_artifacts table is missing; run migrations")

    # Opportunistic GC so TTL is enforced without a separate cron job.
    expire_feature_artifacts(db)

    now = _utcnow()
    expires = now + timedelta(days=ttl_days)
    artifact_id = str(uuid.uuid4())
    request_json = request if isinstance(request, str) else json.dumps(request)
    result_json = result if isinstance(result, str) else json.dumps(result)

    db.conn.execute(
        """
        INSERT INTO user_feature_artifacts (
            artifact_id, user_id, feature, league_id, title,
            request_json, result_json, created_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            user_id,
            feature.strip(),
            league_id,
            title,
            request_json,
            result_json,
            _iso(now),
            _iso(expires),
        ),
    )

    # Cap: keep newest ``cap`` rows for this user+feature.
    kept = db.conn.execute(
        """
        SELECT artifact_id FROM user_feature_artifacts
        WHERE user_id = ? AND feature = ?
        ORDER BY created_at DESC, artifact_id DESC
        """,
        (user_id, feature.strip()),
    ).fetchall()
    if len(kept) > cap:
        overflow_ids = [row[0] for row in kept[cap:]]
        marks = ",".join("?" * len(overflow_ids))
        db.conn.execute(
            f"DELETE FROM user_feature_artifacts WHERE artifact_id IN ({marks})",
            overflow_ids,
        )

    db.conn.commit()
    row = get_feature_artifact(db, artifact_id, user_id)
    assert row is not None
    return row


def _parse_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _artifact_row(row: Any) -> dict[str, Any]:
    item = _row_to_jsonable(dict(row))
    item["request_json"] = _parse_json_field(item.get("request_json"))
    item["result_json"] = _parse_json_field(item.get("result_json"))
    return item


def get_feature_artifact(
    db: FFPyDatabase,
    artifact_id: str,
    user_id: str,
    *,
    include_expired: bool = False,
) -> dict[str, Any] | None:
    if not _table_exists(db, "user_feature_artifacts"):
        return None
    clauses = ["artifact_id = ?", "user_id = ?"]
    params: list[Any] = [artifact_id, user_id]
    if not include_expired:
        clauses.append("expires_at > ?")
        params.append(_iso(_utcnow()))
    cursor = db.conn.execute(
        f"""
        SELECT * FROM user_feature_artifacts
        WHERE {" AND ".join(clauses)}
        """,
        params,
    )
    row = cursor.fetchone()
    return _artifact_row(row) if row else None


def list_feature_artifacts(
    db: FFPyDatabase,
    user_id: str,
    *,
    feature: str | None = None,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    if not _table_exists(db, "user_feature_artifacts"):
        return []

    clauses = ["user_id = ?"]
    params: list[Any] = [user_id]
    if feature:
        clauses.append("feature = ?")
        params.append(feature)
    if not include_expired:
        clauses.append("expires_at > ?")
        params.append(_iso(_utcnow()))

    sql = f"""
        SELECT * FROM user_feature_artifacts
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at DESC
    """
    return [_artifact_row(row) for row in db.conn.execute(sql, params).fetchall()]


def delete_feature_artifact(db: FFPyDatabase, artifact_id: str, user_id: str) -> bool:
    if not _table_exists(db, "user_feature_artifacts"):
        return False
    cur = db.conn.execute(
        "DELETE FROM user_feature_artifacts WHERE artifact_id = ? AND user_id = ?",
        (artifact_id, user_id),
    )
    # Always commit: a zero-row DELETE still opens a SQLite write transaction.
    db.conn.commit()
    return cur.rowcount > 0


def expire_feature_artifacts(db: FFPyDatabase, *, now: datetime | None = None) -> int:
    """Delete artifacts past ``expires_at``. Returns rows removed."""

    if not _table_exists(db, "user_feature_artifacts"):
        return 0
    cutoff = _iso(now or _utcnow())
    cur = db.conn.execute(
        "DELETE FROM user_feature_artifacts WHERE expires_at <= ?",
        (cutoff,),
    )
    db.conn.commit()
    return max(cur.rowcount, 0)


def user_scoped_row_counts(db: FFPyDatabase, user_id: str) -> dict[str, int]:
    """Diagnostic counts for tests / ops."""

    counts: dict[str, int] = {}
    for table in _USER_SCOPED_TABLES:
        if not _table_exists(db, table):
            continue
        row = db.conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        counts[table] = int(row[0]) if row else 0
    return counts


__all__ = [
    "ARTIFACT_CAP_PER_FEATURE",
    "ARTIFACT_TTL_DAYS",
    "delete_feature_artifact",
    "expire_feature_artifacts",
    "export_user_data",
    "get_feature_artifact",
    "list_feature_artifacts",
    "purge_user_data",
    "save_feature_artifact",
    "user_scoped_row_counts",
]
