---
name: "Trend Scout Microservice / Firecrawl"
about: Issue or follow-up related to the Trend Scout Microservice + Firecrawl initiative
title: "trend-scout: "
labels: ""
assignees: ""
---

## Context

Reference: `docs/trend_scout_microservice_plan.md`

This initiative has 11 phases (0–10) tracked as separate branches and PRs. Use this template for:

- Follow-up work discovered during a phase
- Bugs found after a phase is merged
- New Firecrawl targets or new source integrations
- Enhancements to the source health / scoring / backtest pipeline

## Phase(s) affected

- [ ] Phase 0 — plan and scorecard baseline
- [ ] Phase 1 — microservice scaffold
- [ ] Phase 2 — sources migrated
- [ ] Phase 3 — analyzer + scoring + backtest
- [ ] Phase 4 — Celery + Redis Streams
- [ ] Phase 5 — FastAPI surface
- [ ] Phase 6 — Flask proxy + cutover
- [ ] Phase 7 — Firecrawl self-host
- [ ] Phase 8 — Firecrawl standard sources (non-Etsy)
- [ ] Phase 9 — Firecrawl Etsy (throttled, opt-in)
- [ ] Phase 10 — hardening + final scorecard

## Problem

<!-- What is wrong or missing? -->

## Proposed solution

<!-- Concrete description of the change. -->

## Affected modules

- [ ] `services/trend-scout/` (microservice)
- [ ] `services/firecrawl/` (vendored)
- [ ] Flask app — `app/blueprints/trend_scout/`
- [ ] Flask app — `app/celery_app.py`
- [ ] Compose — `docker-compose.yml`
- [ ] Docs — `docs/trend_scout_*.md`, `docs/production_readiness_scorecard.md`
- [ ] Tests — `tests/trend_scout/`, `services/trend-scout/app/tests/`

## Compliance / risk

- [ ] No new Firecrawl target that is hostile to scraping (Etsy-class)
- [ ] No Etsy data displayed on the public website
- [ ] No automated pricing / repricing / order decision driven by Etsy data
- [ ] New audit event(s) defined and wired
- [ ] `FIRECRAWL_RESPECT_ROBOTS_TXT=true` preserved

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Out of scope

<!-- What this issue explicitly does not change. -->
