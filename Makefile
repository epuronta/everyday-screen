.PHONY: install run lint screenshot

install:
	uv sync --all-groups
	uv run playwright install --with-deps chromium
	uv run pre-commit install

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-include "*.html"

screenshot:
	curl -s http://localhost:8000/display.png -o latest_display.png

lint:
	uv run ruff check .
	uv run ruff format --check .
