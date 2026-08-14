FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system .

COPY firecrawl ./firecrawl

USER app

EXPOSE 3002

CMD ["uvicorn", "firecrawl.main:app", "--host", "0.0.0.0", "--port", "3002"]
