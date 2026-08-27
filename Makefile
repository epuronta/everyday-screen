.PHONY: install run up start lint lint-file fix test test-cov screenshot deploy

install:
	uv sync --all-groups
	uv run playwright install --with-deps chromium
	uv run pre-commit install
	
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-include "*.html"

up: run
start: run

screenshot:
	curl -s http://localhost:8000/display.png -o latest_display.png

deploy:
	@test -f deploy/.env || (echo "ERROR: deploy/.env not found — copy deploy/.env.sample and fill in values" && exit 1)
	docker compose -f deploy/compose.yml up --build -d

lint:
	uv run ruff check .
	uv run ruff format --check .

lint-file:
	uv run ruff check $(FILE)
	uv run ruff format --check $(FILE)

fix:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

test-cov:
	uv run pytest --cov --cov-report=term-missing
