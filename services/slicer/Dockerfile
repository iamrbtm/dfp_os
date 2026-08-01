ARG DFPOS_IMAGE_TAG
FROM dfpos-slicer-base:${DFPOS_IMAGE_TAG:-local} AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

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
