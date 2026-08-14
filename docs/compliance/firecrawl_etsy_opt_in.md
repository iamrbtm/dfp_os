# Firecrawl Etsy Tier — Operator Opt-In Acknowledgment

This document captures the operator's acknowledgment of the Etsy's Terms of
Service risk that the Firecrawl Etsy tier carries. The Trend Scout
microservice refuses to start with `FIRECRAWL_ALLOW_ETSY=true` until the
acknowledgment file is recorded.

## Why this exists

Etsy's Terms of Service prohibit scraping the public storefront for
commercial purposes without permission. Their search API permits a limited
subset, but the operator has chosen to attempt the higher-volume path
through Firecrawl. The reasons for choosing this path are recorded in the
conversation history of the trend-scout microservice initiative (Phase 0
plan, Phase 9 decision).

## What enabling Etsy does

When `FIRECRAWL_ALLOW_ETSY=true` (Phase 9 default is `false`) and the
compliance acknowledgment file is fresh:

- A new fetcher key, `firecrawl_etsy`, runs alongside the existing
  standard-tier sources.
- The fetcher applies a random throttle (~1 run in 7 by default) plus a
  min-days gate (default 14 days between successful Etsy fetches).
- Each Firecrawl call dispatches an audit event tagged with the query,
  target URL, and a per-run hash so the operator can later answer "why did
  Etsy run on this Monday?" deterministically.
- Source health rows for Etsy show `Throttled: yes` and a `throttle_reason`
  field that explains why a run was skipped.

## What enabling Etsy does NOT do

- It does NOT touch the public-facing DFS storefront. The price of an
  Etsy-derived opportunity never appears on `/` or any product page.
- It does NOT inform automated pricing decisions. No CI / scheduler reads
  Etsy data and adjusts product prices.
- It does NOT bypass robots.txt globally. Firecrawl's `robots.txt` respect
  is left at the default (on). The Etsy tier uses only the canonical
  search results page which is a `Allow: /` area of Etsy's robots.txt.

## Acknowledgment file

`services/trend-scout/compliance/etsy_opt_in.json` records the
acknowledgment. Write it with:

```bash
uv run flask --app services.trend-scout:create_app acknowledge-etsy-risk \
  --note "Read docs/compliance/firecrawl_etsy_opt_in.md. Risk understood."
```

The file is **gitignored** (`.env`-style local-only). The microservice
boot checks the file's `acknowledged_at` timestamp; if older than 365 days
the microservice refuses to start with `FIRECRAWL_ALLOW_ETSY=true`. Re-run
the CLI yearly.

## Audit trail

When the opt-in is enabled, the microservice dispatches a one-time
`trend_scout.firecrawl.tos_acknowledged` audit event at boot. Every fetch
dispatches `trend_scout.firecrawl.fetch` (or `.error`). Every skipped run
dispatches `trend_scout.firecrawl.throttled`. The weekly credit cap hit
dispatches `trend_scout.firecrawl.credit_cap_hit`.

## Rollback

To disable Etsy after running with it enabled, simply unset
`FIRECRAWL_ALLOW_ETSY` and restart the microservice. The compliance file
becomes irrelevant and may be deleted with
`rm services/trend-scout/compliance/etsy_opt_in.json`. No data cleanup is
required because Etsy data is already excluded from public-facing templates.

## Liability

This acknowledgment creates a permanent, time-stamped record that the
operator knowingly enabled a feature that violates Etsy's published Terms
of Service. The Dude Fish OS / DFPos project assumes no liability for the
operator's choice; the operator assumes responsibility for the legal
consequences of the decision.
