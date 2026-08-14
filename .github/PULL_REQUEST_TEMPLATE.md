---
name: Pull Request
about: Use this template for every PR. Phase work must include the scorecard delta.
title: "[phase-N-short-name] "
labels: ""
assignees: ""
---

## What this PR does

<!-- 1–3 sentences. -->

## Phase

<!-- Required for trend-scout-microservice work. -->

- [ ] This is part of the Trend Scout Microservice + Firecrawl initiative (`docs/trend_scout_microservice_plan.md`).
- [ ] Phase number: `0` / `1` / `2` / `3` / `4` / `5` / `6` / `7` / `8` / `9` / `10`
- [ ] Branch name follows `phase/N-<short-name>`.
- [ ] This PR targets `main` only after the user has approved the phase.

## Scope of this PR

- [ ] Microservice scaffold
- [ ] Source migration
- [ ] Analyzer / scoring / backtest
- [ ] Celery + Redis Streams
- [ ] FastAPI surface
- [ ] Flask proxy + cutover
- [ ] Firecrawl self-host
- [ ] Firecrawl standard sources
- [ ] Firecrawl Etsy (throttled, opt-in)
- [ ] Hardening / docs / scorecard

## Definition of Done

- [ ] Tests pass: `uv run pytest -v --tb=long` (note any env-limited skips)
- [ ] Lint clean: `uv run ruff check .`
- [ ] Format clean: `uv run ruff format --check .`
- [ ] Docker build green for changed services: `docker compose build <service>`
- [ ] Feature flag enforces the new module/endpoint server-side (and a test proves it)
- [ ] Audit events dispatch for every meaningful action (and a test proves it)
- [ ] No hardcoded secrets; no card data fields
- [ ] No breaking change to existing admin UI or API (unless this is the cutover phase)
- [ ] Documentation updated in the same PR
- [ ] User has reviewed the diff and explicitly approved the phase

## Scorecard delta (REQUIRED for trend-scout-microservice phases)

<!--
For every scored area this phase touches, list before/after and a one-line justification.
If this PR does not touch a scored area, write "No scorecard changes."
-->

| Area | Before | After | Justification |
|---|---:|---:|---|
|  |  |  |  |
|  |  |  |  |

## Tests added or changed

<!-- List new/modified test files with a one-line summary each. -->

- `tests/path/to/test_x.py` — covers Y
- `services/trend-scout/app/tests/test_z.py` — covers W

## Audit events added or changed

<!-- List new/modified audit event names. -->

- `trend_scout.X.Y` — emitted from `path/to/file.py:line` on action Z.

## Risk and rollback

<!--
What could go wrong, how do we detect it, and how do we roll back?
Required for any phase that touches the cutover path, the Celery priority config, or the Firecrawl wiring.
-->

- **Risk:**
- **Detection:**
- **Rollback:**

## Out of scope (recorded for follow-up issues)

<!-- Anything discovered during the phase that is intentionally not addressed. -->
