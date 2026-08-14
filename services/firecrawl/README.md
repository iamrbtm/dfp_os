# Firecrawl — Internal Adapter

This directory provides a production-buildable, Firecrawl-compatible internal
scrape adapter for the Dude Fish OS / DFPos Trend Scout pipeline.

The original plan called for vendoring the upstream AGPL-3.0 Firecrawl server.
That vendor step was not completed in Phases 7-10, so this adapter is the
current production path: it implements the narrow API surface Trend Scout uses
(`/health`, `/v2/scrape`, `/v2/search`) and keeps the service profile runnable
without shipping incomplete upstream code.

## Scope

The adapter is intentionally small:

- Authenticated with `Authorization: Bearer $FIRECRAWL_API_KEY`.
- Blocks localhost/internal URLs to avoid SSRF into the Docker network.
- Fetches configured public target pages and returns markdown plus extracted
  link-derived items in the shape the Trend Scout source expects.
- Keeps `/v2/search` present but disabled so generic web search cannot expand
  crawl scope unexpectedly.

If the business later wants upstream Firecrawl, vendor it in a dedicated follow-up
with a real pinned commit SHA, legal review, and a separate security review.

## Files

- `Dockerfile` — production image layered on `python:3.14-slim`, running as a
  non-root user.
- `firecrawl/main.py` — adapter API.
- `firecrawl_client.py` — client used by `services/trend-scout`.
- `UPSTREAM_LOCK.json` — historical record of the deferred upstream vendoring
  target; not an active source lock for this adapter.

## How to rebuild

```bash
cd services/firecrawl
docker build -t dfpos-firecrawl:local .
```

The image runs the API on `3002`. There is no separate worker process in the
adapter implementation.

## Upstream

- Upstream Firecrawl GitHub: https://github.com/firecrawl/firecrawl
- Upstream license: AGPL-3.0. Upstream code is not currently vendored here.
