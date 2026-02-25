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


def depth_color(depth: float) -> tuple[str, str]:
    """Return (stroke_color, fill_color) based on earthquake depth."""
    if depth < 70:
        return "#dc2626", "#ef4444"  # red — shallow
    elif depth < 300:
        return "#ea580c", "#f97316"  # orange — intermediate
    else:
        return "#2563eb", "#3b82f6"  # blue — deep


def mag_radius(mag: float) -> int:
    """Return circle marker radius based on magnitude."""
    return max(4, int(mag * 3))


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


# Register template globals
templates.env.globals["depth_color"] = depth_color
templates.env.globals["mag_radius"] = mag_radius
templates.env.globals["format_time"] = format_time
templates.env.globals["format_time_relative"] = format_time_relative


# --- Default filter values ---


def default_filters() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "start_date": (now - timedelta(days=30)).strftime("%Y-%m-%d"),
        "end_date": now.strftime("%Y-%m-%d"),
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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "quakes": quakes,
            "stats": stats,
            "filters": filters,
            "date_range": date_range,
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
