FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health', timeout=5).raise_for_status()"

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app.main:app", "--keep-alive", "5", "--workers", "2"]
