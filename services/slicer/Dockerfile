FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
RUN mkdir -p /opt/venv && chown appuser:appuser /app /opt/venv

# Install PrusaSlicer and its dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        prusa-slicer curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached unless pyproject.toml / uv.lock change)
COPY --chown=appuser:appuser pyproject.toml uv.lock .python-version ./
USER appuser
RUN --mount=type=cache,uid=1000,gid=1000,target=/tmp/uv-cache \
    uv sync --frozen --no-dev

# Application source
COPY --chown=appuser:appuser . .

EXPOSE 8092

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8092/health/ready || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8092"]
