"""
Seed script — fetch earthquake data from USGS and store in SQLite.

Fetches last 5 years of M4+ earthquakes globally.
USGS API has a 20,000 event limit per query, so we paginate by year.

Usage:
    uv run python seed.py
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DB_PATH = Path(__file__).parent / "data" / "earthquakes.db"
MIN_MAGNITUDE = 4.0
YEARS_BACK = 5


def create_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        DROP TABLE IF EXISTS earthquakes;
        CREATE TABLE earthquakes (
            id TEXT PRIMARY KEY,
            time TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            depth REAL NOT NULL,
            mag REAL NOT NULL,
            mag_type TEXT,
            place TEXT,
            status TEXT,
            tsunami INTEGER DEFAULT 0,
            sig INTEGER,
            felt INTEGER
        );
        CREATE INDEX idx_eq_lat_lng ON earthquakes(lat, lng);
        CREATE INDEX idx_eq_time ON earthquakes(time);
        CREATE INDEX idx_eq_mag ON earthquakes(mag);
    """)


def fetch_year(client: httpx.Client, start: str, end: str) -> list[dict]:
    """Fetch one year of earthquake data from USGS."""
    params = {
        "format": "geojson",
        "starttime": start,
        "endtime": end,
        "minmagnitude": MIN_MAGNITUDE,
        "orderby": "time",
        "limit": 20000,
    }
    resp = client.get(USGS_API, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    return features


def feature_to_row(feature: dict) -> tuple:
    """Convert a GeoJSON Feature to a database row tuple."""
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]  # [lng, lat, depth]

    # USGS time is epoch milliseconds
    time_ms = props.get("time")
    time_iso = (
        datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).isoformat()
        if time_ms
        else None
    )

    return (
        feature["id"],
        time_iso,
        coords[1],  # lat
        coords[0],  # lng
        coords[2] if len(coords) > 2 else 0.0,  # depth km
        props.get("mag", 0.0),
        props.get("magType"),
        props.get("place"),
        props.get("status"),
        props.get("tsunami", 0),
        props.get("sig"),
        props.get("felt"),
    )


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    create_db(conn)

    now = datetime.now(timezone.utc)
    total = 0

    with httpx.Client() as client:
        for i in range(YEARS_BACK):
            end_year = now.year - i
            start_year = end_year - 1

            # Build date boundaries
            if i == 0:
                end_date = now.strftime("%Y-%m-%d")
            else:
                end_date = f"{end_year}-{now.month:02d}-{now.day:02d}"

            start_date = f"{start_year}-{now.month:02d}-{now.day:02d}"

            print(f"Fetching {start_date} → {end_date}...", end=" ", flush=True)

            features = fetch_year(client, start_date, end_date)
            rows = [feature_to_row(f) for f in features]

            conn.executemany(
                """INSERT OR IGNORE INTO earthquakes
                   (id, time, lat, lng, depth, mag, mag_type, place, status, tsunami, sig, felt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()

            print(f"{len(rows)} events")
            total += len(rows)

    # Final stats
    cursor = conn.execute("SELECT COUNT(*) FROM earthquakes")
    db_count = cursor.fetchone()[0]
    print(f"\nDone. {total} fetched, {db_count} unique events in database.")
    print(f"Database: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

    conn.close()


if __name__ == "__main__":
    main()
