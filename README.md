# everyday-screen

A home hallway display that renders useful at-a-glance info: weather, electricity spot prices, and public transport schedules.

## Architecture

The display device is a static e-ink screen that periodically fetches and shows a remote image. All the logic lives on the backend:

1. **FastAPI** serves an HTML template populated with live data
2. On request, **Playwright** screenshots the rendered page into a PNG (cached for 1 minute)
3. The display device polls `/display.png`, and is told when to come back

**The display side is dumb** — no logic, no state, just an image viewer. All computation (SVG paths, threshold positions, departure reachability) is pre-computed in Python and passed as plain values to the template. Keep it that way.

## Modules

```
app/main.py          — FastAPI app, routes, parallel data fetching
app/renderer.py      — Playwright screenshot (default 1200×825)
app/electricity.py   — spot-hinta.fi API + sparkline SVG pre-computation
app/weather.py       — FMI WFS API (observations + Harmonie forecast)
app/transport.py     — Digitransit GraphQL (HSL stops + departures)
app/menu.py          — shared MenuDay/Dish dataclasses and cache helper
app/menu_aromi.py    — Aromi (aromi.hel.fi) lunch fetcher — POST API, no auth required
app/menu_amica.py    — Compass Group / Amica menu fetcher (scrapes __INITIAL_MENU__ from the restaurant page HTML)
app/refresh.py       — decides how long the device should sleep before its next fetch
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

## E-ink legibility

The physical display looks significantly different from a browser preview. Light grays that read fine in the browser become marginal or invisible on e-ink. `make screenshot` is not a reliable proxy — when in doubt, check against the device.

Two factors dominate legibility on this display:

- **Font weight.** Bold is clearly readable at distance; regular weight at small sizes largely disappears. Bold is not decoration — it's required for anything the user needs to actually read.
- **Gray shade.** Treat `--g3` and lighter as invisible for practical purposes. `--g0`/`--g1` for readable content, `--g2` for secondary content. Anything lighter is separator-level at best.

**Default to dark + bold** when adding new elements. Pull back only if there's a specific reason — don't start from light/small and hope it's fine.

**Text tier classes** implement these rules. Use them on all text elements instead of raw `--gN` variables:

| Class | Use for | Properties |
|---|---|---|
| `.text-primary` | Key info the user must read (line numbers, identifiers) | `--g0`, bold |
| `.text-secondary` | Supporting info, readable but not primary (event times, headsigns) | `--g2` |
| `.text-label` | Section separator labels (day names, period headers) — decorative | `--g2`, 0.85rem |
| `.text-ghost` | Footer status line — smaller than body text, still legible | `--g2`, 0.9rem |

Default body text (inheriting `--g0`) needs no class. SVG text uses `fill` not `color` — set `fill` values directly.

## Running locally

```bash
make up          # start uvicorn on :8000 with live reload (aliases: start, run)
make screenshot  # save latest_display.png from the running server
make lint        # ruff check + format --check
make fix         # ruff autofix + format
make test        # pytest
make test-cov    # pytest with a term-missing coverage report
```

Tests cover the pure logic — parsers, geometry, the refresh schedule. The
network fetchers, their module-level caches and the Playwright render are
deliberately untested; see `TODO.md`.

There's also a `/` route that serves the raw HTML — useful for inspecting layout without going through the PNG render.

## Configuration

Copy `app/settings_local.py` from `app/settings_local.sample.py` and fill in values:

- `TIMEZONE` — IANA tz, default `Europe/Helsinki`
- `FMI_CITY` — city name for FMI weather API
- `DIGITRANSIT_API_KEY` — from portal-api.digitransit.fi
- `HSL_STOPS` — list of `StopConfig(code, lines=None, walk_time_minutes=0)`
- `API_TOKEN` — optional, required as `?token=` on all endpoints
- `AMICA_URL` — Compass Group restaurant page URL; leave empty to disable (`menu_amica.py`)
- `AROMI_URL` — full Aromi API endpoint URL (e.g. `https://aromi.hel.fi/.../api/Common/Restaurant/RestaurantMeals`); leave empty to disable
- `AROMI_RESTAURANT_ID` — restaurant GUID from the Aromi URL
- `AROMI_DINER_GROUP_ID` — diner group GUID (get from `GET /api/GetRestaurantPublicDinerGroups`)
- `REFRESH_OVERRIDE_SECONDS` — fixed refresh interval in seconds, bypassing the schedule; `0` uses the schedule. Set this on a dev instance so iterating doesn't mean waiting out a 10-minute band

## Refresh schedule

The device has no opinion about how often to wake up. Every `/display.png`
response carries an `X-Next-Refresh` header holding the number of seconds the
device should sleep before asking again:

```
GET /display.png?token=...&battery=3.72
200 OK
Content-Type: image/png
X-Next-Refresh: 180
```

It rides on the image response rather than sitting behind its own endpoint,
because a second request per wake means a second connection and TLS handshake —
a real share of the awake-radio time the schedule exists to reduce.

Bands are local wall-clock and identical every day (`app/refresh.py`):

| Local time | Interval |
|---|---|
| 06:00–09:00 | 3 min |
| 09:00–22:00 | 10 min |
| 22:00–06:00 | 30 min |

Two rules shape the returned value:

- **Clamped to the next band edge**, so a wake never overshoots into the
  following band. Without it, 05:45 sleeps its full 30 minutes and misses the
  first quarter of the morning cadence.
- **Floored at 60s**, because clamping can land arbitrarily close to an edge.

Roughly 154 wakes/day, against 288 for the flat 5-minute interval this
replaced.

The optional `battery` query parameter is the device's raw voltage. It's
rendered into the image footer alongside a percentage, so the number on screen
comes from the same wake that reported it. The percentage uses a linear
3.0–4.2 V map and is known to read low — a full battery reports well under
100% — which is why the raw voltage is shown next to it.

## Deployment

Runs on a VPS via Docker Compose with Traefik as the reverse proxy. `settings_local.py` gets baked into the Docker image at build time.

Copy `deploy/.env.sample` to `deploy/.env` and fill in values, then:

```bash
git pull && make deploy
```