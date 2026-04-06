# everyday-screen

A home hallway display that renders useful at-a-glance info: weather, calendar events, public transport schedules, and more.

## Architecture

The display device is a static e-ink screen that periodically fetches and shows a remote image. All the logic lives on the backend:

1. **FastAPI** serves an HTML template populated with live data
2. On request, **Playwright** screenshots the rendered page into a PNG (cached for 1 minute)
3. The display device polls the backend for the latest image

This keeps the display side dumb — no logic, no updates, just an image viewer.

### Deployment

Runs on a VPS via Docker Compose:

- **`app`** — FastAPI + Playwright renderer. Internal only, never exposed publicly.
- **`nginx`** — Public-facing reverse proxy. Terminates TLS and validates a static token before proxying image requests to `app`.

The display device polls `https://<host>/display.png?token=<token>`. FastAPI is not directly reachable from the internet.

## Configuration

Copy `deploy/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `FMI_CITY` | yes | City name for FMI weather (e.g. `Helsinki`) |
| `DIGITRANSIT_API_KEY` | yes | API key from [portal-api.digitransit.fi](https://portal-api.digitransit.fi) |
| `HSL_STOPS` | yes | Comma-separated HSL stop codes as shown on the physical sign (e.g. `H4534,H4260`) |
| `HSL_LINES` | no | Comma-separated line filter (e.g. `550,65A`). If omitted, all lines at the stop are shown. |

Stop codes are printed on the physical stop signs and can also be found on the [HSL map](https://www.hsl.fi/en).

## Dependencies

`uv` as usual.

Note: On a server, use `uv run playwright install --with-deps chromium` to install the headless chromium we need for rendering images.

## Running locally

```bash
# Start the FastAPI server (with live reload)
make run

# Render the current display to latest_display.png
make screenshot
```