"""
Earthquake Explorer — FastAPI app.

Routes:
    GET /           — Full page with map + sidebar
    GET /quakes     — HTMX endpoint: returns markers + table rows (hx-swap-oob)
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import get_earthquakes, get_stats, get_date_range

BASE_DIR = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# --- Template helpers ---


def mag_color(mag: float) -> tuple[str, str]:
    """Return (stroke_color, fill_color) based on earthquake magnitude."""
    if mag >= 7:
        return "#991b1b", "#dc2626"  # dark red — major
    elif mag >= 6:
        return "#dc2626", "#ef4444"  # red — strong
    elif mag >= 5:
        return "#ea580c", "#f97316"  # orange — moderate
    else:
        return "#ca8a04", "#eab308"  # gold — light


def mag_radius(mag: float) -> int:
    """Return circle marker radius based on magnitude."""
    return max(3, int(mag * 2))


def format_time(iso_str: str) -> str:
    """Format ISO time string to short display."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16] if iso_str else ""


def format_time_relative(iso_str: str) -> str:
    """Format ISO time string to relative display (e.g. '3 days ago')."""
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = now - dt
        if delta.days > 365:
            years = delta.days // 365
            return f"{years}y ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months}mo ago"
        elif delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        else:
            return f"{delta.seconds // 60}m ago"
    except (ValueError, TypeError):
        return ""


def date_to_ms(date_str: str) -> int:
    """Convert YYYY-MM-DD to Unix milliseconds."""
    return int(
        datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        * 1000
    )


def format_date_label(date_str: str) -> str:
    """Format YYYY-MM-DD to 'Feb 25, 2026'."""
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{months[dt.month - 1]} {dt.day}, {dt.year}"


# Register template globals
templates.env.globals["mag_color"] = mag_color
templates.env.globals["mag_radius"] = mag_radius
templates.env.globals["format_time"] = format_time
templates.env.globals["format_time_relative"] = format_time_relative


# --- Default filter values ---

ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000
ONE_DAY_MS = 24 * 60 * 60 * 1000


def default_filters() -> dict:
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "start_label": format_date_label(start_date),
        "end_label": format_date_label(end_date),
        "start_ts": date_to_ms(start_date),
        "end_ts": date_to_ms(end_date),
        "min_mag": 4.0,
    }


def parse_bbox(bbox_str: str) -> tuple[float, float, float, float]:
    """Parse Leaflet bbox string: 'min_lng,min_lat,max_lng,max_lat'."""
    parts = [float(x) for x in bbox_str.split(",")]
    min_lng, min_lat, max_lng, max_lat = parts
    return min_lat, max_lat, min_lng, max_lng


# --- Routes ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    filters = default_filters()
    date_range = get_date_range()

    quakes = get_earthquakes(
        start_date=filters["start_date"],
        end_date=filters["end_date"],
        min_mag=filters["min_mag"],
    )
    stats = get_stats(
        start_date=filters["start_date"],
        end_date=filters["end_date"],
        min_mag=filters["min_mag"],
    )

    # Add timestamps to date_range for the slider
    date_range["min_ts"] = date_to_ms(date_range["min_date"])
    date_range["max_ts"] = date_to_ms(date_range["max_date"])

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "quakes": quakes,
            "stats": stats,
            "filters": filters,
            "date_range": date_range,
            "one_year_ms": ONE_YEAR_MS,
            "one_day_ms": ONE_DAY_MS,
        },
    )


@app.get("/quakes", response_class=HTMLResponse)
async def get_quakes(
    request: Request,
    bbox: str = "-180,-90,180,90",
    start: str | None = None,
    end: str | None = None,
    min_mag: float = 4.0,
):
    filters = default_filters()
    start_date = start or filters["start_date"]
    end_date = end or filters["end_date"]

    min_lat, max_lat, min_lng, max_lng = parse_bbox(bbox)

    quakes = get_earthquakes(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
        start_date=start_date,
        end_date=end_date,
        min_mag=min_mag,
    )
    stats = get_stats(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
        start_date=start_date,
        end_date=end_date,
        min_mag=min_mag,
    )

    # Return markers (primary swap target) + table rows + stats (via hx-swap-oob)
    markers_html = templates.get_template("partials/markers.html").render(quakes=quakes)
    rows_html = templates.get_template("partials/rows.html").render(quakes=quakes)
    stats_html = templates.get_template("partials/stats.html").render(stats=stats)

    # Primary target is #source (markers), OOB targets are #table-wrap and #stats
    return HTMLResponse(
        content=(
            markers_html
            + f'\n<div id="table-wrap" hx-swap-oob="innerHTML"><table><thead><tr>'
            + "<th>Mag</th><th>Location</th><th>Depth</th><th>When</th>"
            + f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
            + f'\n<div id="stats" hx-swap-oob="innerHTML">{stats_html}</div>'
        )
    )
