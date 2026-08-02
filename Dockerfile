# Frontend assets: prebuilt Node image so nodejs/npm never touch the runtime
# image or the apt step. Only builds Tailwind CSS + copies GSAP into dist.
FROM node:22-slim AS assets

WORKDIR /assets

COPY package.json package-lock.json postcss.config.js tailwind.config.js ./
RUN --mount=type=cache,target=/root/.cache/npm \
    npm ci --no-audit --no-fund

# Tailwind scans Jinja templates for utility classes. Copy templates into the
# asset stage before building CSS, otherwise Docker builds purge most styles.
COPY app/static ./app/static
COPY app/templates ./app/templates
RUN npm run build

# Base runtime: pre-built image (Dockerfile.base) with system packages already
# installed, so app rebuilds skip the slow apt-get step.
FROM ${BASE_IMAGE:-dfpos-base:local} AS base

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Python dependencies (cached unless pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock .python-version ./
RUN mkdir -p /opt/venv && chown appuser:appuser /opt/venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Application source + assets built in the node stage
COPY --chown=appuser:appuser . .
COPY --from=assets /assets/app/static/dist ./app/static/dist
RUN mkdir -p uploads instance \
    && chown -R appuser:appuser uploads instance

USER appuser
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "app:create_app()"]

FROM base AS dev
USER root
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
USER appuser
