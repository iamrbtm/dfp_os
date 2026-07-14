# Trend Scout Production Readiness — Gap Remediation Roadmap

## Goal

Close the 17 production-readiness gaps identified in the Trend Scout audit so the feature is operable, observable, configurable, and integrated enough for daily business use.

## Current State

Trend Scout has 12 completed roadmap phases (fuzzy matching, explainability, persisted scores, configurable weights, action workflows, product analytics, source health, backtesting, admin UX, compliance guardrails, production verification, Product Studio button) and 45 passing tests.

A targeted audit found the following gaps, grouped by severity:

### Critical

| # | Gap | Impact |
|---|---|---|
| 1 | No REST API endpoints | External tools and automation can't read reports, scores, or source health |
| 2 | No Flask CLI command | Operations must use admin UI or Celery — no `flask trend-scout run` |
| 3 | No notifications when important trends found | Admin must check dashboard to discover `print_now` recommendations |
| 4 | No Celery task monitor | Background pipeline progress is tracked per-tab via session, no monitor dashboard |

### Major

| # | Gap | Impact |
|---|---|---|
| 5 | No score history visualization | Phase 3 persists scores but UI never shows trends over time |
| 6 | No dedicated settings page | Weights buried in generic Settings; no dedicated Trend Scout config UI |
| 7 | No data retention / snapshot cleanup | TrendSnapshot rows accumulate unbounded per pipeline run |
| 8 | No "add to market prep" integration | Recommendations can't become packing list items or prep tasks |
| 9 | No CSV export | Backtest numbers can't be downloaded for offline analysis |
| 10 | No dedicated report detail page | Past reports are truncated to a 4-column table summary |
| 11 | No rate-limit retry logic | Only BGG handles HTTP 429; Etsy, Pinterest, TikTok can permanently fail a run |

### Moderate

| # | Gap | Impact |
|---|---|---|
| 12 | Opportunity matrix capped at 50 rows | No pagination or load-more |
| 13 | No dismiss/ignore for opportunities | False positives stay in every report forever |
| 14 | No auto-refresh after pipeline run | Page needs manual reload to show new report |
| 15 | No backtest scheduling | Must manually trigger calibration; no automated periodic tuning |
| 16 | No report comparison mode | Can't diff current vs previous report side by side |
| 17 | No print job ↔ opportunity linking | Can't trace which recommendation created a print job |

---

## Milestone 1: Platform Access

Make Trend Scout operable from terminal and API.

### Phase 1: CLI Command

**Objective:** Run the pipeline and read reports from the terminal.

| Task | Description | Output |
|---|---|---|
| Add `flask trend-scout run` | Execute the full pipeline via CLI | Terminal-driven pipeline |
| Add `flask trend-scout status` | Show latest report summary, source health, last-run time | Quick status check |
| Add `flask trend-scout backtest` | Run backtest from terminal | Terminal-driven calibration |
| Add audit logging | Log CLI-initiated pipeline runs | Audit trail |
| Add tests | Verify CLI commands create reports, handle errors, and respect feature flags | CLI tests |

**Definition of Done:** An operator can run, inspect, and backtest Trend Scout entirely from the terminal without opening a browser.

### Phase 2: REST API Endpoints

**Objective:** Expose Trend Scout data and actions through the REST API.

| Task | Description | Output |
|---|---|---|
| Register `trend-reports` resource | List and read Trend Reports via `/api/v1/trend-reports` | API resource |
| Register `trend-opportunities` resource | List, filter, sort opportunities via `/api/v1/trend-opportunities` | API resource |
| Register `trend-source-health` resource | Read source health records via `/api/v1/trend-source-health` | API resource |
| Add pipeline trigger endpoint | `POST /api/v1/trend-reports/run` to start a pipeline run | API trigger |
| Add action endpoints | `POST /api/v1/trend-opportunities/{id}/print-now`, etc. | Remote action |
| Add API docs / OpenAPI tags | Document Trend Scout endpoints in the API docs | Discoverable API |
| Add permission/scope enforcement | Require `trend_scout:read` / `trend_scout:write` scopes | Secure API |
| Add tests | Verify CRUD, filtering, sorting, auth, and action endpoints | API tests |

**Definition of Done:** External tools, scripts, and integrations can read Trend Scout data and trigger actions through the same REST API used by every other module.

---

## Milestone 2: Reliability & Observability

Make Trend Scout robust, monitorable, and safe to run unattended.

### Phase 3: Notifications & Alerts

**Objective:** Proactively inform the admin when important trends emerge.

| Task | Description | Output |
|---|---|---|
| Define notification triggers | New `print_now` opportunity, score spike, source failure, backtest completed | Alert rules |
| Add in-app notification panel | Show Trend Scout notifications in a global notification center | In-app alerts |
| Add email notification | Send digest or immediate email for critical triggers (opt-in) | Email alerts |
| Add notification preferences UI | Let admin choose which triggers produce which channel | Configurable alerts |
| Add audit logging | Log every notification dispatch | Audit trail |
| Add tests | Verify triggers, channels, and opt-out handling | Notification tests |

**Definition of Done:** The admin learns about important trend findings without manually checking the Trend Scout page.

### Phase 4: Celery Task Monitor

**Objective:** Provide a dashboard for background pipeline tasks.

| Task | Description | Output |
|---|---|---|
| Create task monitor view | Show running, completed, failed, and queued Trend Scout Celery tasks | Monitor UI |
| Show task metadata | Duration, source, started-at, error message, retry count | Task detail |
| Add retry/cancel actions | Retry a failed pipeline or cancel a running one | Task management |
| Replace session-based tracking | Store pipeline progress in a persistent TaskRun model instead of Flask session | Robust progress |
| Add audit logging | Log pipeline start, completion, failure, retry, and cancellation | Audit trail |
| Add tests | Verify task lifecycle, error states, and retry flow | Monitor tests |

**Definition of Done:** An admin can see the status, history, and logs of every Trend Scout pipeline run from a dedicated monitor page, and can retry or cancel runs.

### Phase 5: Rate-Limit Retry Logic

**Objective:** External source fetches survive transient rate limits.

| Task | Description | Output |
|---|---|---|
| Add retry decorator to source fetchers | Wrap Etsy, Pinterest, TikTok, Google Trends fetches with exponential backoff | Resilient sources |
| Standardize HTTP 429 handling | Share retry logic across all source fetchers (currently only BGG has it) | Consistent behavior |
| Log rate-limit events | Record 429 occurrences in source health records | Observable throttling |
| Add source health state for rate-limited | Show "rate_limited" as distinct from "failed" in source health UI | Actionable status |
| Add tests | Mock 429 responses and verify retry and fallback behavior | Retry tests |

**Definition of Done:** A transient rate limit from any external source does not permanently fail the pipeline run.

### Phase 6: Data Retention & Cleanup

**Objective:** Prevent unbounded growth of TrendSnapshot and opportunity score tables.

| Task | Description | Output |
|---|---|---|
| Define retention policy | Keep last N reports (e.g. 52 weeks) or auto-prune after configurable age | Retention rules |
| Add prune CLI command | `flask trend-scout prune --keep 52` to archive old snapshots | CLI cleanup |
| Add automatic prune hook | Run prune after each pipeline run or via Celery periodic task | Auto-cleanup |
| Add archival table or file export | Move pruned data to a cold storage table or JSON export before deleting | Recoverable archive |
| Add audit logging | Log every prune action with counts deleted and archived | Audit trail |
| Add tests | Verify prune logic, boundary conditions, and no accidental data loss | Prune tests |

**Definition of Done:** Trend Scout data has a bounded storage footprint and old snapshots are automatically archived or pruned.

---

## Milestone 3: Admin UX Deepening

Make the Trend Scout interface production-quality for daily use.

### Phase 7: Score History Visualization

**Objective:** Show how opportunity scores change over time (unlocks the value of Phase 3).

| Task | Description | Output |
|---|---|---|
| Add score history query | Query `trend_opportunity_scores` grouped by candidate, ordered by report date | History data |
| Add sparkline per row | Inline mini chart showing score trend for each opportunity | At-a-glance trend |
| Add full score history chart | Chart.js line chart on drill-down or detail panel for a single product | Detailed trend |
| Add "biggest movers" view | Filter/sort by largest positive or negative score change since last report | Score change focus |
| Add tests | Verify history query, chart data serialization, and edge cases | Visualization tests |

**Definition of Done:** An admin can see at a glance whether a product's opportunity score is rising, falling, or stable over the last N reports.

### Phase 8: Dedicated Settings Page

**Objective:** Give Trend Scout its own configuration UI instead of burying weights in the general Settings page.

| Task | Description | Output |
|---|---|---|
| Create `/admin/trend-scout/settings` route | Dedicated settings page for Trend Scout | Settings page |
| Add weight sliders | Score component weights with visual feedback (sliders, validation, reset-to-default) | Tunable weights |
| Add source enable/disable toggles | Per-source on/off toggle with health status indicator | Source control |
| Add scoring profile selector | Save and load named scoring profiles (e.g. "Market Mode", "Online Mode") | Profile management |
| Add validation | Prevent invalid weight combinations, warn on extreme values | Safe tuning |
| Add audit logging | Log weight changes, profile swaps, and source toggles | Audit trail |
| Add tests | Verify settings save, load, validation, and profile switching | Settings tests |

**Definition of Done:** An admin can tune Trend Scout's behavior — weights, sources, profiles — from a dedicated page without editing code or hunting through generic settings.

### Phase 9: Report Detail & Comparison Page

**Objective:** Provide a full report view and side-by-side comparison.

| Task | Description | Output |
|---|---|---|
| Create `/admin/trend-scout/reports/<id>` | Dedicated report detail page with full opportunity matrix, source health, and metadata | Report detail |
| Add summary header | Report ID, run date, pipeline duration, source count, opportunity count, scoring version | Report summary |
| Add expandable per-row detail | Full score breakdown, source contributions, change from previous row | Row drilldown |
| Add comparison mode | Side-by-side diff view of current report vs a selected previous report | Report diff |
| Highlight changes | Color-code score deltas (green up, red down, gray unchanged) | At-a-glance diff |
| Add CSV export per report | Download the full report as CSV from the detail page | Report export |
| Add tests | Verify report detail, comparison, and CSV export | Report tests |

**Definition of Done:** Past reports are fully viewable, comparable, and exportable — not just truncated table summaries.

### Phase 10: Matrix UX Polish

**Objective:** Eliminate friction points in the main opportunity matrix.

| Task | Description | Output |
|---|---|---|
| Add pagination | Replace `[:50]` with server-side paginated query (page + per_page params) | Browseable matrix |
| Add CSV export button | Export the current matrix (filtered/sorted view) as CSV | Matrix export |
| Add dismiss/ignore | Add `dismissed` flag or join table so false positives stay hidden across reports | Persistent suppression |
| Add undo-dismiss | Allow re-showing dismissed opportunities | Recoverable dismiss |
| Add auto-refresh on pipeline complete | After HTMX progress hits 100%, reload or swap in the new report without manual refresh | Seamless update |
| Add tests | Verify pagination, CSV output, dismiss persistence, and refresh behavior | UX tests |

**Definition of Done:** The matrix page handles large data sets, supports export, lets users dismiss noise, and refreshes automatically after a pipeline run.

---

## Milestone 4: Workflow Integration

Close the loop from trend discovery to production action.

### Phase 11: Backtest Scheduling

**Objective:** Automate periodic score calibration.

| Task | Description | Output |
|---|---|---|
| Add Celery periodic task | Run backtest monthly (configurable interval) | Scheduled calibration |
| Store calibration results | Persist accuracy metrics, bad-signal lists, and tuning hints per run | Calibration history |
| Add calibration comparison | Show how accuracy changed since the last calibration run | Accuracy trends |
| Add alert on regression | Notify admin if prediction accuracy drops below a threshold | Regression alerts |
| Add audit logging | Log automated backtest runs, results, and regressions | Audit trail |
| Add tests | Verify scheduled run, result storage, and regression detection | Schedule tests |

**Definition of Done:** The scoring model is automatically re-calibrated against real sales data on a regular schedule, and the admin is alerted if accuracy degrades.

### Phase 12: Print Job ↔ Opportunity Linking

**Objective:** Trace every print job back to the Trend Scout recommendation that created it.

| Task | Description | Output |
|---|---|---|
| Add `trend_opportunity_id` to PrintJob model | Optional FK or metadata field linking a print job to a trend opportunity | Traceable print jobs |
| Store link on "Print Now" action | Populate the link when action is taken from Trend Scout | Automatic trace |
| Add trace in PrintJob admin view | Show "Created from Trend Scout opportunity" with link back | Bidirectional navigation |
| Add "View print jobs" in Trend Scout | Show which opportunities have resulted in print jobs and their status | Action outcome visibility |
| Add audit logging | Log when a print job is linked to or unlinked from an opportunity | Audit trail |
| Add tests | Verify link creation, display, and navigation | Trace tests |

**Definition of Done:** Every `print_now` recommendation that becomes a print job carries a link back to the trend opportunity that prompted it, and the admin can see the outcome from both sides.

### Phase 13: Market Prep Integration

**Objective:** Turn Trend Scout recommendations into market prep tasks.

| Task | Description | Output |
|---|---|---|
| Add "Add to market prep" action | Button in Trend Scout that creates prep tasks for an upcoming market | Prep generation |
| Select target market | Choose which upcoming market to add items to | Market selection |
| Generate packing list items | Convert recommended products into suggested packing-list entries with quantities | Packing suggestions |
| Add quantity suggestion | Use score, velocity, and previous market sales to suggest how many to bring | Data-backed quantity |
| Add prep task for reprints | Generate "Print X units of [product]" prep tasks based on recommended quantities | Reprint tasks |
| Add audit logging | Log when opportunities are added to market prep | Audit trail |
| Add tests | Verify prep generation, market selection, and quantity suggestions | Integration tests |

**Definition of Done:** A high-scoring "print now" opportunity can flow from Trend Scout → market prep → packing list → print job in a few clicks.

---

## Recommended Build Order

1. Phase 1: CLI Command
2. Phase 2: REST API Endpoints
3. Phase 3: Notifications & Alerts
4. Phase 4: Celery Task Monitor
5. Phase 6: Data Retention & Cleanup
6. Phase 5: Rate-Limit Retry Logic
7. Phase 7: Score History Visualization
8. Phase 8: Dedicated Settings Page
9. Phase 9: Report Detail & Comparison Page
10. Phase 10: Matrix UX Polish
11. Phase 11: Backtest Scheduling
12. Phase 12: Print Job ↔ Opportunity Linking
13. Phase 13: Market Prep Integration

## Practical Milestones

### Milestone A: Operable From Every Interface (Phases 1–2)

Trend Scout can be run and queried from CLI, REST API, and admin UI. External scripts and tools are unblocked.

### Milestone B: Run Unattended With Confidence (Phases 3–6)

The pipeline can run on a schedule without requiring the admin to watch it. Rate limits and data growth are handled automatically. Failures and findings produce notifications.

### Milestone C: Production-Grade Decision Board (Phases 7–10)

The admin can tune the model, see score history, compare reports, export data, and suppress noise. The UX handles daily use without friction.

### Milestone D: Closed-Loop Business Workflow (Phases 11–13)

Trends aren't just displayed — they become print jobs, prep tasks, packing lists, and calibrated scores. The loop from "market signal" → "production decision" → "physical product" is fully traceable.

## Highest-Value Next Phase

Start with **Phase 1 (CLI Command)** .

Reason: It's the quickest to implement (one new file, no schema changes) and immediately unblocks terminal-driven operation. Phase 2 (REST API) reuses the same service-layer patterns and can follow directly.
