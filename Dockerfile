FROM node:22-slim AS assets

WORKDIR /assets

COPY package.json package-lock.json postcss.config.js tailwind.config.js ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY app/static ./app/static
COPY app/templates ./app/templates
RUN npm run build


FROM dfpos-base:local AS base

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --chown=appuser:appuser . .
COPY --from=assets /assets/app/static/dist ./app/static/dist
COPY --chown=appuser:appuser gunicorn.conf.py ./

RUN mkdir -p uploads instance \
    && chown -R appuser:appuser uploads instance

COPY --chown=root:root scripts/docker_entrypoint.sh /usr/local/bin/docker_entrypoint.sh
RUN chmod +x /usr/local/bin/docker_entrypoint.sh

# The entrypoint runs as root so it can chown bind-mounted volumes
# (which Docker creates as root) before the app process starts.
ENTRYPOINT ["/usr/local/bin/docker_entrypoint.sh"]
EXPOSE 5000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]


FROM base AS dev

USER root
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
USER appuser

ENV GUNICORN_RELOAD=true \
    GUNICORN_WORKERS=1 \
    GUNICORN_PRELOAD=false
