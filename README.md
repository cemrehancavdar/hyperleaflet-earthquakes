# Earthquake Explorer

**[Live Demo](https://hyperleaflet-earthquakes.fly.dev/)**

81,000+ earthquakes (M4+, 5 years) from USGS, visualized on an interactive map. Filter by time range, magnitude, and map bounds.

Built with [hyperleaflet](https://github.com/cemrehancavdar/hyperleaflet), HTMX, FastAPI, and SQLite. The total custom JavaScript is a date formatting function.

## Stack

- **FastAPI** + Jinja2 — serves HTML, no JSON API
- **HTMX** — filtering, live updates via `hx-get` + `hx-swap-oob`
- **Hyperleaflet** — map + markers from `data-*` attributes, reactive via MutationObserver
- **Surreal.js** — inline behaviors (slider debounce, row click)
- **toolcool-range-slider** — time range web component
- **SQLite** — 23 MB, seeded from USGS FDSNWS API

## Run locally

```bash
uv sync
uv run python seed.py          # fetch USGS data into SQLite (~2 min)
uv run fastapi dev src/main.py
```

## Deploy

```bash
fly deploy
```

Database is seeded at Docker build time.

## License

MIT
