FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps before copying app code so this layer is cached across deploys
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# --with-deps handles the OS-level libraries Chromium needs (saves maintaining our own apt list)
RUN uv run playwright install --with-deps chromium

COPY app/ ./app/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
