FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
RUN chown appuser:appuser /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache

COPY --chown=appuser:appuser pyproject.toml uv.lock ./
USER appuser
RUN --mount=type=cache,uid=1000,gid=1000,target=/tmp/uv-cache \
    uv sync --frozen --no-dev

COPY --chown=appuser:appuser . .

EXPOSE 8090

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
