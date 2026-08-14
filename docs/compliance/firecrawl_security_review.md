# Firecrawl Self-Host — Security Review

This document records the security posture of the Firecrawl self-host and the
patched defaults we apply before promoting the upstream image to production.
Phase 7 ships this review together with the vendored `services/firecrawl/`
skeleton. Phase 10 re-reviews after every upstream upgrade.

## Upstream defaults (what we change)

We self-host the Firecrawl API + worker per the upstream
[`SELF_HOST.md`](https://github.com/firecrawl/firecrawl/blob/main/SELF_HOST.md).
The upstream baseline has the following gaps that we close:

| Upstream default | Our patched value | Why |
|---|---|---|
| `USE_DB_AUTHENTICATION=false` | `USE_DB_AUTHENTICATION=true` | Without auth, anyone who can reach `http://firecrawl:3002` can scrape arbitrary URLs through our infrastructure and burn our Firecrawl credits. |
| `BULL_AUTH_KEY` unset | `BULL_AUTH_KEY=<generated-secret>` | The queue admin UI is otherwise accessible with no password. Disabling the UI is an additional safeguard. |
| `BULL_QUEUE_ADMIN_ENABLED=true` | `BULL_QUEUE_ADMIN_ENABLED=false` | Same reason. UI is for local debugging only. |
| Postgres `nuq` data on non-persistent volume | `nuq_data` Docker volume mounted | Upstream compose does not persist NuQ data. Our build will lose all queued scrapes on container restart. |
| RabbitMQ on non-persistent volume | `rabbitmq_data` Docker volume mounted | Same reason. |
| Playwright browser cache in container | `playwright_cache` Docker volume mounted | Avoid re-downloading ~300 MB on each boot. |
| Default Scraping engine (basic fetch) | Bundled Playwright | Some Firecrawl targets in Phase 8 are JS-rendered. |
| No API model provider | No provider wired by default | AI features are explicit opt-in. We never enable them in DFPos because we have a local GPT model integration in the microservice. |

## Secret rotation

- `FIRECRAWL_API_KEY` is rotated every 90 days.
- `BULL_AUTH_KEY` is rotated every 90 days.
- Both values live in the production `.env` file and are loaded by
  `docker compose`; they are never committed to source control.

## Network exposure

- The Firecrawl API listens on `firecrawl-api:3002` inside the `dfpos_default`
  Docker network. It is **not** published to the host (no `ports:` directive).
- The Playwright service is **not** published either; only the API can reach it.
- Only the Trend Scout microservice (`services/trend-scout`) connects to the
  Firecrawl API. The Flask app does not (the microservice handles Firecrawl).

## Resource limits

Production docker-compose overrides (will land in Phase 10):

- `firecrawl-api`: 2 GB RAM, 1 vCPU
- `firecrawl-playwright`: 4 GB RAM, 2 vCPU (browser pools are heavy)
- `firecrawl-redis`: 1 GB RAM
- `firecrawl-rabbitmq`: 1 GB RAM
- `firecrawl-nuq`: 1 GB RAM

## robots.txt respect

Firecrawl respects `robots.txt` by default. We keep
`FIRECRAWL_RESPECT_ROBOTS_TXT=true` in production. Any new target that
disagrees with this is gated behind a feature flag (Phase 9 introduces the
Etsy opt-in, which is the only target that requires operator acknowledgement
to bypass robots.txt on a strict subset of pages).

## Compliance trail

Each Firecrawl call dispatches an audit event via the audit-log microservice:

- `trend_scout.firecrawl.fetch` (every successful call)
- `trend_scout.firecrawl.error` (every failed call)
- `trend_scout.firecrawl.throttled` (Etsy skipped because of the random gate)
- `trend_scout.firecrawl.credit_cap_hit` (weekly cap reached)
- `trend_scout.firecrawl.tos_acknowledged` (one-shot at boot when Etsy opt-in is on)

The audit events list the target, query, target URL, robots.txt respect
status, and credit estimate. Operators can replay an Etsy run after the fact
by inspecting the audit log.

## Known gaps (deferred to Phase 10)

1. **No HTTPS internal**. Firecrawl speaks HTTP inside the Docker network.
   The Trend Scout microservice talks to it over plain HTTP. Acceptable for
   the internal network model; would need mTLS for true zero-trust.
2. **No rate limiting at the gateway**. The microservice controls per-target
   rate limits; a misbehaving target could still exceed Firecrawl's monthly
   credit budget. The weekly credit cap (`FIRECRAWL_WEEKLY_CREDIT_CAP`) is
   enforced client-side in Phase 9.
3. **No auth in the Playwright service**. Internal-only; Cloudflare-style
   filtering not applied.

## Out-of-scope

- Commercial Firecrawl Cloud. We self-host to control spend and stay
  AGPL-compliant.
- Multi-tenant isolation. Firecrawl is single-tenant per deployment; it is
  not designed to be shared across multiple businesses.
- Custom scrapers. We use the standard scrape + extract endpoints. Per-site
  custom adapters are a Phase 10 follow-up if Firecrawl's LLM extractor
  proves unreliable for specific sites.
