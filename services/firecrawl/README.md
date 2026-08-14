# Firecrawl — Self-Hosted Subtree

This directory vendors the Firecrawl open-source self-host container images
the Dude Fish OS / DFPos Trend Scout pipeline runs against. The vendored code
is pinned to a specific upstream release tag (recorded in
`UPSTREAM_LOCK.json`); upgrades go through a deliberate process documented
in `docs/compliance/firecrawl_security_review.md`.

## Scope (what we vendor)

We vendor the **Firecrawl API + worker container** service so we can:

- control upgrade cadence
- patch the security defaults before reaching production
  (`USE_DB_AUTHENTICATION=true`, persistent volumes, queue admin disabled)
- ship AGPL-3.0 compliance notes together with the code

We do **not** vendor the UI (`firecrawl-ui`) or example apps. They are not
used by the DFPos pipeline.

## Files

- `Dockerfile` — minimal production image layered on `python:3.14-slim` with
  non-root `appuser`. The upstream `Dockerfile` is the source of truth; this
  copy adds the security defaults documented in the security review.
- `docker-compose.yml` — local-only override of the upstream compose that
  hardens the API. The docker-compose file in the repo root is what
  production uses.
- `app/services/firecrawl/` — Python client used by the Trend Scout
  microservice to call Firecrawl. Vendored as a fallback so the
  `firecrawl-py` SDK lives next to our code in case upstream becomes
  unreachable.
- `UPSTREAM_LOCK.json` — pinned upstream commit SHA + tag.
- `SECURITY_PATCHES.md` — list of patches we apply to the upstream image
  before promoting it to production.

## How to rebuild

```bash
cd services/firecrawl
docker build -t dfpos-firecrawl:local .
```

The image runs the API on `3002` and the workers in background mode.

## Upstream

- GitHub: https://github.com/firecrawl/firecrawl
- License: AGPL-3.0 (the upstream Firecrawl server). The SDK (`firecrawl-py`)
  is MIT and we depend on it through `services/trend-scout/pyproject.toml`.
