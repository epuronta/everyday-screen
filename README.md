# everyday-screen

A home hallway display that renders useful at-a-glance info: weather, calendar events, public transport schedules, and more.

## Architecture

The display device is a static e-ink screen that periodically fetches and shows a remote image. All the logic lives on the backend:

1. **FastAPI** serves an HTML template populated with live data
2. On request, **Playwright** screenshots the rendered page into a PNG (cached for 1 minute)
3. The display device polls the backend for the latest image

This keeps the display side dumb — no logic, no updates, just an image viewer.

### Deployment

Runs on a VPS via Docker Compose with Traefik as the reverse proxy. `deploy/.env` only needs `DOMAIN` — Traefik uses it for routing and TLS.

To deploy:

```bash
# First time: create app/settings_local.py on the server (see Configuration below)
git pull && make deploy
```

`make deploy` builds the Docker image from the local working directory, so `settings_local.py` gets baked in automatically.

## Configuration

Copy `app/settings_local.sample.py` to `app/settings_local.py` and fill in your values. The sample file documents each setting.

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