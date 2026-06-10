# MedSync API + Worker shared image
FROM python:3.11-slim

# uv: fast dependency resolution + install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first (cached layer) using only the lockfile + manifest
COPY pyproject.toml ./
RUN uv sync --extra dev --no-install-project

# Copy application source and install the project itself
COPY . .
RUN uv sync --extra dev

EXPOSE 8000

CMD ["uvicorn", "medsync.main:app", "--host", "0.0.0.0", "--port", "8000"]
