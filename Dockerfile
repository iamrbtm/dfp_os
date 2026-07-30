FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# System dependencies (cached unless this layer changes)
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential curl nodejs npm \
        tesseract-ocr tesseract-ocr-eng \
        imagemagick poppler-utils \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached unless pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock .python-version ./
RUN mkdir -p /opt/venv && chown appuser:appuser /opt/venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Node dependencies (cached unless package.json changes)
COPY package.json package-lock.json postcss.config.js tailwind.config.js ./
RUN npm ci

# Application source + build assets
COPY . .
RUN mkdir -p app/static/dist \
    && npm run build \
    && mkdir -p uploads instance \
    && chown -R appuser:appuser /app uploads instance

USER appuser
EXPOSE 5000
CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "app:create_app()"]

FROM base AS dev
USER root
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
USER appuser
