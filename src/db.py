"""
Database queries for earthquake data.

All queries use parameterized SQL against a local SQLite database.
No ORM — just sqlite3 and plain dicts.
"""

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "earthquakes.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Module-level connection (FastAPI is single-process, SQLite reads are safe)
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = get_connection()
    return _conn


def get_earthquakes(
    min_lat: float = -90,
    max_lat: float = 90,
    min_lng: float = -180,
    max_lng: float = 180,
    start_date: str | None = None,
    end_date: str | None = None,
    min_mag: float = 4.0,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Query earthquakes with bbox, time range, and magnitude filters."""
    conn = _get_conn()

    conditions = [
        "lat BETWEEN ? AND ?",
        "lng BETWEEN ? AND ?",
        "mag >= ?",
    ]
    params: list[Any] = [min_lat, max_lat, min_lng, max_lng, min_mag]

    if start_date:
        conditions.append("time >= ?")
        params.append(start_date)
    if end_date:
        # Add a day to make end_date inclusive
        conditions.append("time < ?")
        params.append(end_date + "T23:59:59")

    params.append(limit)

    sql = f"""
        SELECT id, time, lat, lng, depth, mag, mag_type, place, tsunami, sig, felt
        FROM earthquakes
        WHERE {" AND ".join(conditions)}
        ORDER BY time DESC
        LIMIT ?
    """

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_stats(
    min_lat: float = -90,
    max_lat: float = 90,
    min_lng: float = -180,
    max_lng: float = 180,
    start_date: str | None = None,
    end_date: str | None = None,
    min_mag: float = 4.0,
) -> dict[str, Any]:
    """Get summary stats for filtered earthquakes."""
    conn = _get_conn()

    conditions = [
        "lat BETWEEN ? AND ?",
        "lng BETWEEN ? AND ?",
        "mag >= ?",
    ]
    params: list[Any] = [min_lat, max_lat, min_lng, max_lng, min_mag]

    if start_date:
        conditions.append("time >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("time < ?")
        params.append(end_date + "T23:59:59")

    sql = f"""
        SELECT
            COUNT(*) as count,
            ROUND(AVG(mag), 1) as avg_mag,
            ROUND(MAX(mag), 1) as max_mag,
            ROUND(AVG(depth), 0) as avg_depth
        FROM earthquakes
        WHERE {" AND ".join(conditions)}
    """

    row = conn.execute(sql, params).fetchone()
    return (
        dict(row) if row else {"count": 0, "avg_mag": 0, "max_mag": 0, "avg_depth": 0}
    )


def get_date_range() -> dict[str, str]:
    """Get the earliest and latest dates in the database."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT MIN(time) as min_date, MAX(time) as max_date FROM earthquakes"
    ).fetchone()
    return {
        "min_date": row["min_date"][:10] if row["min_date"] else "2021-01-01",
        "max_date": row["max_date"][:10] if row["max_date"] else "2026-02-26",
    }
