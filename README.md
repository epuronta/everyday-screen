# everyday-screen

A home hallway display that renders useful at-a-glance info: weather, calendar events, public transport schedules, and more.

## Architecture

The display device is a static screen that periodically fetches and shows a remote image. All the logic lives on the backend:

1. **FastAPI** serves an HTML template populated with live data
2. **Playwright** screenshots the rendered page into a PNG
3. The display device polls the backend for the latest image

This keeps the display side dumb — no logic, no updates, just an image viewer.

## Dependencies

`uv` as usual.

Note: On a server, use `uv run playwright install --with-deps chromium` to install the headless chromium we need for rendering images.

## Running

```bash
# Start the FastAPI server
uv run uvicorn app:app --host 0.0.0.0 --port 8000

# Render the current display to latest_display.png
uv run python renderer.py
```