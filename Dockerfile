FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* .python-version ./
RUN pip install --no-cache-dir uv
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY package.json postcss.config.js tailwind.config.js ./
RUN npm install

COPY . .

RUN mkdir -p app/static/dist uploads instance
RUN npm run build:css || true

EXPOSE 5000

CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:5000", "app:create_app()"]
