# everyday-screen

A home hallway display that renders useful at-a-glance info: weather, electricity spot prices, and public transport schedules.

## Architecture

The display device is a static e-ink screen that periodically fetches and shows a remote image. All the logic lives on the backend:

1. **FastAPI** serves an HTML template populated with live data
2. On request, **Playwright** screenshots the rendered page into a PNG (cached for 1 minute)
3. The display device polls `/display.png`

**The display side is dumb** — no logic, no state, just an image viewer. All computation (SVG paths, threshold positions, departure reachability) is pre-computed in Python and passed as plain values to the template. Keep it that way.

## Modules

```
app/main.py          — FastAPI app, routes, parallel data fetching
app/renderer.py      — Playwright screenshot (default 1200×825)
app/electricity.py   — spot-hinta.fi API + sparkline SVG pre-computation
app/weather.py       — FMI WFS API (observations + Harmonie forecast)
app/transport.py     — Digitransit GraphQL (HSL stops + departures)
app/settings.py      — imports everything from settings_local.py
app/templates/
  display.html       — single Jinja2 template, all CSS inline
  icons/             — SVG icons, included via {% include %}
```

Each data module has its own in-memory cache: weather 10 min, electricity 1 h, transport 1 s.

## Design

**E-ink palette.** 8 grayscale CSS variables only: `--g0` (black) → `--g7` (white). No colors, no shadows.

**Layout.** CSS grid, 2 columns:
- Top-left: clock/date
- Bottom-left: weather — day blocks (Aamu 06–12, Ilta 12–20) with icons and temp range, plus hourly precipitation chart (stacked boxes, 1/mm, capped at 5mm), labels in Finnish
- Right: transport departures (up to 5 per stop, greyed out if unreachable given walk time)
- Bottom full-width: electricity sparkline

**Electricity sparkline.** 48h fixed window (today 00:00 → tomorrow 23:00). Y-axis runs 0 → max price rounded up to next 10c, with grid lines every 10c. `CHEAP_THRESHOLD` / `EXPENSIVE_THRESHOLD` are only used for `classify()` (the icon next to the current price), not for chart lines.

## Running locally

```bash
make up          # start uvicorn on :8000 with live reload (aliases: start, run)
make screenshot  # save latest_display.png from the running server
make lint        # ruff check + format --check
make fix         # ruff autofix + format
```

There's also a `/` route that serves the raw HTML — useful for inspecting layout without going through the PNG render.

## Configuration

Copy `app/settings_local.py` from `app/settings_local.sample.py` and fill in values:

- `TIMEZONE` — IANA tz, default `Europe/Helsinki`
- `FMI_CITY` — city name for FMI weather API
- `DIGITRANSIT_API_KEY` — from portal-api.digitransit.fi
- `HSL_STOPS` — list of `StopConfig(code, lines=None, walk_time_minutes=0)`
- `API_TOKEN` — optional, required as `?token=` on all endpoints

## Deployment

Runs on a VPS via Docker Compose with Traefik as the reverse proxy. `settings_local.py` gets baked into the Docker image at build time.

Copy `deploy/.env.sample` to `deploy/.env` and fill in values, then:

```bash
git pull && make deploy
```