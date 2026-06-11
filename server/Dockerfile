# MedSync API + Worker shared image
FROM python:3.11-slim

# uv: fast dependency resolution + install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keep the virtualenv OUTSIDE /app so a dev bind-mount of ./server:/app does not
# clobber it. PATH points at it so alembic/uvicorn/celery resolve without uv.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first (cached layer) from the manifest + lockfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --extra dev --no-install-project --frozen

# Copy application source and install the project itself.
COPY . .
RUN uv sync --extra dev --frozen

EXPOSE 8000

CMD ["uvicorn", "medsync.main:app", "--host", "0.0.0.0", "--port", "8000"]
