.PHONY: install run lint screenshot deploy

install:
	uv sync --all-groups
	uv run playwright install --with-deps chromium
	uv run pre-commit install

run:
	set -a && . ./.env && set +a && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-include "*.html"

screenshot:
	curl -s http://localhost:8000/display.png -o latest_display.png

deploy:
	@test -f .env || (echo "ERROR: .env not found — copy .env.sample and fill in values" && exit 1)
	docker compose -f deploy/compose.yml up --build -d

lint:
	uv run ruff check .
	uv run ruff format --check .
