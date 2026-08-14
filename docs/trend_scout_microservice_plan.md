# Trend Scout Microservice + Firecrawl Plan

Status: **Executed — production cutover completed on `phase/10-hardening-and-scorecard`**
Branch: `phase/10-hardening-and-scorecard`
Owners: Jeremy (DFPos)
Source: condensed from the full planning conversation logged in chat history.

---

## 1. Why we are doing this

Trend Scout currently lives inside the Flask monolith (`app/services/ai/trend_scout/`, `app/tasks/trend_scout.py`, `app/models/trend.py`). It is resource-heavy when it runs (10 source fetchers, NLP embeddings, DBSCAN, GPT synthesis) and competes with POS, checkout, and admin traffic for CPU, RAM, and DB connections.

Two changes are bundled into one initiative because they share infrastructure and would otherwise mean two consecutive cutovers and double the operational risk:

1. **Extract Trend Scout into its own microservice** so it can scale, fail, and deploy independently of the main app.
2. **Add a self-hosted Firecrawl source family** to cover the 3D marketplace gap (Cults3D, Thangs, STLFinder, CGTrader, MyMiniFactory trending pages) and to attempt a periodic Etsy signal under strict opt-in and throttling.

The existing 10 direct sources (`internal_demand`, `makerworld`, `printables`, `myminifactory`, `etsy` (API), `pinterest`, `tiktok`, `google_trends`, `reddit`, `bgg`, `last30days`) keep running as-is and are migrated to the new service unchanged. Firecrawl is added on top.

## 2. Architecture (final)

```
Flask app (admin UI + existing API)
   │  HTTP + Bearer token (httpx proxy)
   ▼
services/trend-scout (FastAPI :8093, Python 3.14, async SQLAlchemy 2.x + asyncpg)
   │
   ├── enqueue_trend_run() ──► Redis Streams (DB 2)
   │                                    │
   │                                    ▼
   │                            stream_worker (drains + batched writes)
   │                                    │
   │                                    ├── 10 existing source fetchers (ThreadPoolExecutor, max 4)
   │                                    ├── 7 new Firecrawl targets
   │                                    ├── analyzer (velocity, momentum, embeddings, DBSCAN)
   │                                    ├── GPT synthesis + deterministic fallback
   │                                    └── batched INSERTs to Postgres
   ▼
Postgres DB `trend_scout` (own logical DB on the shared Postgres container)

Celery beat (existing) ──► app.tasks.dispatch_trend_scout_run ──HTTP POST──► services/trend-scout
                                                                                │
                                                                                ▼
                                                          Celery queue `trend_scout` (low priority)
                                                                                │
                                                                                ▼
                                                          trend-scout-worker (concurrency=1)
                                                          + main worker (-Q default,trend_scout)
```

### Key infrastructure choices

- **Shared Postgres, new logical DB `trend_scout`** — same pattern as `intelligence` and `audit`. Provisioned via `docker/postgres/init/`.
- **Redis DB 2** for Firecrawl trend scout streams (DB 0 = audit outbox, DB 1 = Celery broker, DB 2 = new).
- **Celery task lives in the microservice** (option B). Beat stays in the main app and dispatches via a 5-line HTTP POST.
- **Queue partition `trend_scout`, priority 1/10** — Trend Scout is low priority. Main app's default queue stays at high priority. A dedicated `trend-scout-worker` container subscribes only to the low-priority queue with `concurrency=1`; the existing main worker is also allowed to drain it (low-priority) when idle so the dedicated worker is not wasted.
- **Firecrawl-compatible internal adapter** in `services/firecrawl/`, hardened with bearer auth, SSRF blocking for local/internal URLs, bounded response size, and a narrow `/v2/scrape` API surface. Upstream Firecrawl vendoring remains a future legal/security-reviewed option; production no longer references an incomplete upstream checkout.

## 3. Firecrawl target matrix (final)

| Target | Tier | Default | Opt-in flag | Rate limit | Pages/run | Source weight | Source health label |
|---|---|---|---|---|---|---|---|
| `etsy` | Throttled | OFF | `FIRECRAWL_ALLOW_ETSY` | 30s | 20 | 0.4× | `firecrawl_etsy` |
| `cults3d` | Standard | ON when `FIRECRAWL_ENABLED` | none | 5s | 30 | 1.0× | `firecrawl_cults3d` |
| `thangs` | Standard | ON | none | 5s | 30 | 0.9× | `firecrawl_thangs` |
| `stlfinder` | Standard | ON | none | 5s | 30 | 0.8× | `firecrawl_stlfinder` |
| `cgtrader` | Standard | ON | none | 5s | 20 | 0.9× | `firecrawl_cgtrader` |
| `mmf_trending` | Standard (fallback) | ON | none | 5s | 20 | 1.0× | `firecrawl_mmf` |
| `general` | Standard | ON | none | 10s | 10 | 0.5× | `firecrawl_general` |

**MyMiniFactory fallback semantics:** the direct API source (`myminifactory`) runs first; if it returns an error or zero items, the Firecrawl `mmf_trending` target runs as a fallback. Never in parallel. Source health records both attempts distinctly.

**Etsy throttling:** two-gate gate, deterministic for audit. `_should_run_target("etsy")` returns True only if:
1. A deterministic pseudo-random draw (seeded by the run's Celery task ID) is below `FIRECRAWL_ETSY_RUN_PROBABILITY` (default 0.15 ≈ 1-in-7).
2. The last successful Etsy fetch was at least `FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS` (default 14) days ago.

Every skipped Etsy run dispatches an audit event (`trend_scout.firecrawl.throttled`) with the run id, draw value, and reason — the operator can later ask "why did Etsy run on this Monday?" and the answer is reproducible from the audit log.

## 4. Etsy risk posture (operator-acknowledged)

The operator has chosen to attempt scraped Etsy data despite the Etsy's Terms of Service prohibiting commercial scraping without permission. The official API path was rejected because the scope of intended use is not compatible with what Etsy's API permits. Mitigations:

- **Default off.** `FIRECRAWL_ALLOW_ETSY=false` until the operator explicitly opts in.
- **One-time acknowledgment required.** `uv run flask --app services/trend-scout:create_app acknowledge-etsy-risk --note "..."` writes `services/trend-scout/compliance/etsy_opt_in.json`. The microservice refuses to start with `FIRECRAWL_ALLOW_ETSY=true` unless that file exists.
- **Permanent audit trail.** `trend_scout.firecrawl.tos_acknowledged` fires once at boot if opt-in is enabled. Every fetch and every skip is audited.
- **Hard limits in code, not just config.** `MAX_PAGES_PER_RUN=20`, `MIN_INTERVAL_SECONDS=30`, weekly credit cap.
- **Source weight 0.4×** so Etsy can never dominate scoring even when it works.
- **Never displayed on the public website.** A test walks the template tree and asserts no Etsy-derived content reaches a public-facing response.
- **No automated pricing, repricing, or order decisions** driven by Etsy data.
- **Firecrawl respects `robots.txt` by default** — operator must keep `FIRECRAWL_RESPECT_ROBOTS_TXT=true`; the only path that runs against Etsy is the explicit opt-in tier.
- **`docs/compliance/firecrawl_etsy_opt_in.md`** documents the legal posture and the operator's decision.

## 5. Phase plan (11 phases, 0–10)

Every phase ends with: tests green, lint clean, Docker green, scorecard updated, committed to a per-phase branch, pushed, user-approved.

| Phase | Branch | Scope |
|---|---|---|
| 0 | `phase/0-plan-and-scorecard` | This doc, scorecard baseline, PR template, issue template, CI skeleton |
| 1 | `phase/1-ms-scaffold` | `services/trend-scout/` scaffolded from `intelligence` template, Dockerfile, Alembic, FastAPI app, config, security, Celery instance, health endpoint, compose wiring, env vars |
| 2 | `phase/2-sources-migrated` | All 10 existing sources moved, fetcher pipeline async-refactored, source health persistence, models migrated |
| 3 | `phase/3-analyzer-and-scoring` | Async analyzer, weights module, backtest, calibration, audit dispatch wrapper, AI provider |
| 4 | `phase/4-celery-and-streams` | Redis Streams worker, source fetcher pool, Celery tasks in microservice, low-priority queue, dispatch tasks in main app |
| 5 | `phase/5-api-and-routes` | All 8 API resources with Pydantic schemas, scope enforcement, OpenAPI |
| 6 | `phase/6-flask-proxy-and-cutover` | Flask routes become httpx proxy, old files deleted, hard cutover, runbook |
| 7 | `phase/7-firecrawl-self-host` | Vendored Firecrawl compose, hardened, security review doc |
| 8 | `phase/8-firecrawl-standard-sources` | Cults3D, Thangs, STLFinder, CGTrader, MMF fallback, general web discovery |
| 9 | `phase/9-firecrawl-etsy-throttled` | Etsy tier, throttling, compliance CLI, boot-time refusal, audit `tos_acknowledged` |
| 10 | `phase/10-hardening-and-scorecard` | Full test suite, final scorecard, docs, end-to-end production-readiness gate |

## 6. Quality bar (every phase)

- `uv run ruff check .` — passes
- `uv run ruff format --check .` — passes
- `uv run pytest -v --tb=long` — passes (within environment limits; documented when DB-dependent tests cannot run)
- `docker compose build` — green for changed services
- `docs/production_readiness_scorecard.md` — updated for the area
- Feature flag enforcement
- Audit logging for meaningful actions
- No hardcoded secrets
- No card data fields
- No breaking change to existing admin UI or API until the cutover phase
- Documentation updated in the same PR as the change

## 7. Production-readiness definition (explicit)

A phase is "production-ready" when:

1. Tests are green (per environment capability).
2. Lint and format are clean.
3. Docker build is green for changed services.
4. Feature flags enforce the new module/endpoint server-side.
5. Audit events dispatch for every meaningful action.
6. No hardcoded secrets; no card data.
7. The system fails loud, not silent.
8. The compliance trail is permanent and auditable (especially for Etsy).
9. The Celery priority actually works (test verifies a high-priority task dispatched while the worker is busy with a trend-scout task gets picked up next).
10. The Redis Streams worker survives a Postgres outage (Redis buffers, no data loss up to cap, replay on recovery).
11. Source health auto-degrades chronically failing sources without operator intervention.
12. Documentation is updated.
13. The user has reviewed the diff, the test output, and the scorecard delta and has explicitly approved the phase.

## 8. Open items to revisit at later phases

- **Residential proxy for Etsy** (deferred): when Etsy IP block becomes chronic, a residential proxy is a possible future upgrade. Not committed.
- **Other marketplaces' ToS review** (deferred): CGTrader, STLFinder, Thangs, Cults3D are friendlier to crawlers than Etsy, but a per-site ToS review belongs in a follow-up if any of them are chronically failing.
- **General "open web" discovery target** (`general`) — included in Phase 8 by default; trivial to disable via env.
- **Public display of any Firecrawl data** — banned. No Etsy, no other Firecrawl data on the public site, ever. Enforced by a test.

## 9. Files this initiative will touch (full list)

### Created
- `services/trend-scout/` (new microservice, ~30 files)
- `services/firecrawl/` (production-buildable Firecrawl-compatible internal adapter)
- `docs/trend_scout_microservice_plan.md` (this file)
- `docs/compliance/firecrawl_etsy_opt_in.md`
- `docs/compliance/firecrawl_security_review.md`
- `docs/runbooks/trend_scout_microservice_cutover.md`
- `services/trend-scout/compliance/etsy_opt_in.json` (gitignored, written by CLI)
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/trend_scout_microservice.md`
- `.github/workflows/ci.yml` (with `trend-scout-tests` job)
- `services/trend-scout/app/tests/` (microservice tests)
- `docker/postgres/init/01-init-databases.sh` (DB provisioning)

### Modified
- `docker-compose.yml` (new services, new env, new volumes, queue flags on existing workers)
- `.env.example` (new env vars)
- `app/celery_app.py` (priority/queue config, new dispatch tasks in `include`)
- `app/blueprints/trend_scout/routes.py` (httpx proxy)
- `app/blueprints/api/routes.py` (trend-scout API proxy)
- `app/__init__.py` (drop direct trend-scout blueprint import)
- `app/module_registry.py` (preserve entry, update route table)
- `app/cli.py` (drop trend_scout_group)
- `pyproject.toml` (main app dependency cleanup is tracked separately where shared deps still serve other modules)
- `docs/production_readiness_scorecard.md` (appended per-phase delta)
- `docs/trend_scout_setup.md` (rewrite for new architecture)
- `docs/AI Design Trend Scout Implementation.md` (mark superseded)
- `AGENTS.md` (services table)
- `ARCHITECTURE.md` (data flow diagram)
- `README.md` (how to run/test/develop the microservice)

### Deleted
- `app/services/ai/trend_scout/` (moved)
- `app/services/trend_scout_weights.py` (moved)
- `app/services/trend_scout_backtest.py` (moved)
- `app/models/trend.py` (moved)
- `app/tasks/trend_scout.py` (moved)
- `app/tasks/trend_calibration.py` (moved)

### Execution notes from production cutover pass

- The Flask admin Trend Scout routes now read/write through `app.services.trend_scout_proxy.TrendScoutProxy`.
- Old monolith ORM models, analyzer, source fetchers, weights/backtest/calibration/history/prune helpers, Celery tasks, schemas, and monolith tests were deleted.
- The generic Flask API no longer exposes `trend-reports`, `trend-opportunity-scores`, or `trend-source-health` as main-database ORM resources; Trend Scout data is served by the microservice API.
- Product Studio no longer imports the monolith analyzer. It reads the latest product-linked score from the microservice.
- `.env.example` now includes the Firecrawl adapter variables.
- `docker compose --profile firecrawl` starts the internal adapter (`firecrawl-api`) instead of requiring incomplete upstream sidecars.

## 10. Audit events (full list for this initiative)

```
trend_scout.pipeline.started
trend_scout.pipeline.completed
trend_scout.pipeline.failed
trend_scout.source.fetched
trend_scout.source.failed
trend_scout.source.throttled           (Etsy skipped)
trend_scout.credit_cap_hit
trend_scout.firecrawl.tos_acknowledged  (Etsy only, fires once at boot)
trend_scout.calibration.completed
trend_scout.calibration.failed
trend_scout.print_now.created
trend_scout.print_now.skipped
trend_scout.opportunity.dismissed
trend_scout.opportunity.undismissed
trend_scout.create_product.redirected
trend_scout.flag_clearance
trend_scout.flag_license_review
trend_scout.flag_retire
trend_scout.settings.weights_saved
trend_scout.settings.source_toggled
trend_scout.settings.profile_loaded
trend_scout.settings.profile_saved
trend_scout.task_cancelled
trend_scout.task_retried
```

## 11. Env vars (full new set)

```env
# Microservice
TREND_SCOUT_SERVICE_URL=http://trend-scout:8093
TREND_SCOUT_INTERNAL_API_TOKEN=...
TREND_SCOUT_POSTGRES_DB=trend_scout
TREND_SCOUT_POSTGRES_USER=trend_scout
TREND_SCOUT_POSTGRES_PASSWORD=...
TREND_SCOUT_REDIS_URL=redis://redis:6379/2
TREND_SCOUT_CELERY_BROKER_URL=redis://redis:6379/1
TREND_SCOUT_CELERY_RESULT_BACKEND=redis://redis:6379/1
TREND_SCOUT_AUDIT_LOG_BASE_URL=http://audit-log:8090
TREND_SCOUT_AUDIT_LOG_TOKEN=...

# Firecrawl
FIRECRAWL_ENABLED=false
FIRECRAWL_API_URL=http://firecrawl-api:3002
FIRECRAWL_API_KEY=
FIRECRAWL_BULL_AUTH_KEY=
FIRECRAWL_NUQ_USER=
FIRECRAWL_NUQ_PASSWORD=
FIRECRAWL_RESPECT_ROBOTS_TXT=true
FIRECRAWL_WEEKLY_CREDIT_CAP=2000

# Etsy-specific throttling
FIRECRAWL_ALLOW_ETSY=false
FIRECRAWL_ETSY_RUN_PROBABILITY=0.15
FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS=14
FIRECRAWL_ETSY_MIN_INTERVAL_SECONDS=30
FIRECRAWL_ETSY_MAX_PAGES_PER_RUN=20
```

## 12. References

- `docs/AI Design Trend Scout Implementation.md` — original implementation spec, marked superseded at Phase 10
- `docs/trend_scout_setup.md` — rewritten at Phase 10 for the new architecture
- `docs/Trend Scout Production Roadmap.md` — historical, superseded by this plan
- `services/intelligence/` — template for the new microservice
- `services/audit-log/` — template for auth + outbox + telemetry
- `https://github.com/firecrawl/firecrawl` — vendored at pinned release tag
