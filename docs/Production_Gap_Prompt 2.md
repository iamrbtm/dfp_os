You are an expert Senior DevSecOps Engineer, Principal QA Automation Engineer, and Lead Flask/Python engineer.

  I am attaching a markdown audit report that lists production-readiness, security, QA, and architecture findings for the `dfp_os`
  codebase. Your job is to implement the remediation plan from that report in clear phases.

  ## Project Context

  Project: Dude Fish OS / DFPos
  Stack: Flask, Jinja2, SQLAlchemy, MariaDB, Flask-Migrate/Alembic, Flask-Login, Flask-WTF, Tailwind, HTMX, Docker Compose, Pytest, uv.

  Before making changes:

  1. Read `AGENTS.md`.
  2. Read `DESIGN.md`.
  3. Read `ARCHITECTURE.md`, `TODO.md`, and `PROMPTS.md` if present.
  4. Read the attached audit markdown completely.
  5. Inspect the actual repo before editing.
  6. Preserve existing user work. Do not revert unrelated changes.
  7. Work phase by phase.
  8. At the end of each phase, run the relevant tests/checks, commit / push to git and summarize what changed.

  Do not merely document fixes. Implement them.

  ---

  # Phase 0: Baseline Inspection and Safety Check

  ## Goal

  Confirm the current state of the repo before changing anything.

  ## Tasks

  1. Inspect git status.
  2. Read the audit report fully.
  3. Confirm each listed issue still exists in the codebase.
  4. Identify any existing tests that already cover the affected areas.
  5. Identify likely migrations/config/env changes needed.
  6. Create a short execution checklist for Phases 1-8.

  ## Verification

  Run:

  ```bash
  uv run ruff check app services tests
  uv run python -m py_compile app/config.py app/__init__.py

  If either fails, record the failures but continue into the relevant phase.

  ## Deliverable

  A short baseline note listing:

  - Confirmed findings
  - Existing failing checks
  - Any risky files already modified in the worktree
  - Exact plan for Phase 1

  ———

  # Phase 1: Critical Financial Integrity Fixes

  ## Goal

  Fix the highest-risk business logic issues around POS sales, totals, payment records, inventory deduction, and audit behavior.

  ## Findings Covered

  - POS checkout trusting client-side prices/totals
  - Financial actions not failing closed when audit dispatch fails

  ## Tasks

  ### POS Financial Integrity

  1. Make the server authoritative for product prices.
  2. Product sale price must come from the database, not the browser.
  3. Reject:
      - negative prices
      - negative discounts
      - negative taxes
      - negative quantities
      - zero quantities
      - malformed cart items
      - negative totals

  4. Require cash received to cover sale total.
  5. Keep custom items and custom deposits supported, but validate them strictly.
  6. Ensure inventory deduction still happens correctly.
  7. Ensure POS sale creates order/payment records correctly.

  ### Audit Fail-Closed

  1. Add a clear AuditDispatchError or equivalent.
  2. Respect config for fail-closed behavior.
  3. Ensure POS sale/refund and other critical financial workflows fail closed when configured.
  4. Make sure audit failure does not silently disappear for critical actions.
  5. Add tests that mock audit failure.

  ## Tests Required

  Add or update tests for:

  - tampered product price rejected or ignored in favor of DB price
  - negative quantity rejected
  - negative discount rejected
  - insufficient cash rejected
  - valid cash sale still succeeds
  - audit failure blocks critical financial action when fail-closed is enabled
  - audit failure does not block when fail-closed is disabled, if that mode is intentionally supported

  ## Verification

  Run:

  uv run pytest tests -k "pos or audit"
  uv run ruff check app/services/pos.py app/services/audit_client.py tests

  ## Deliverable

  Summarize:

  - Files changed
  - POS integrity fixes
  - Audit fail-closed behavior
  - Tests added
  - Any remaining financial workflow risks

  ———

  # Phase 2: API Authorization and Workflow Hardening

  ## Goal

  Prevent API tokens and generic REST endpoints from bypassing permissions or domain workflows.

  ## Findings Covered

  - API tokens defaulting to full access
  - API tokens able to mint more unrestricted tokens
  - Deactivated users’ API tokens remaining valid
  - Generic REST CRUD bypassing receipt, POS, and inventory workflows

  ## Tasks

  ### API Token Hardening

  1. Empty scopes must not mean full access.
  2. Full access must require an explicit privileged scope.
  3. Deactivated users’ API tokens must stop working.
  4. API token creation through API must not allow privilege escalation.
  5. Add or update token creation validation.
  6. Review existing tokens/scopes migration implications.

  ### Domain Workflow Protection

  1. Generic API CRUD must not mutate protected workflow fields.
  2. Receipt approval must go through receipt approval service.
  3. POS refund/void/status transitions must go through POS service.
  4. Inventory quantity changes must go through inventory movement/adjustment service.
  5. Reject protected fields in generic PUT/PATCH.
  6. Add explicit action endpoints only where needed and route them through services.

  ## Tests Required

  Add or update tests for:

  - empty-scope token cannot access protected API
  - explicit scope is required
  - deactivated user token is rejected
  - scoped token cannot mint broader token
  - generic receipt PUT cannot approve a receipt
  - generic POS sale PUT cannot refund/void/change status
  - generic inventory PUT cannot directly alter quantity
  - proper service workflow still works

  ## Verification

  Run:

  uv run pytest tests -k "api or token or receipt or inventory or pos"
  uv run ruff check app/blueprints/api app/utils/auth.py app/models/api_token.py tests

  ## Deliverable

  Summarize:

  - API token behavior changes
  - Protected workflow fields
  - Tests added
  - Any backwards compatibility concerns

  ———

  # Phase 3: Upload, Receipt File, and Sensitive Data Access Security

  ## Goal

  Harden receipt uploads, parser boundaries, and access controls for receipt files/images.

  ## Findings Covered

  - Receipt upload validation is extension-only
  - Uploaded files are passed into native parsers
  - Receipt image endpoint lacks role/ownership enforcement

  ## Tasks

  ### Upload Validation

  1. Replace extension-only validation with content-based validation.
  2. Enforce MIME/type checks.
  3. Enforce size checks.
  4. Add parser safety limits:
      - PDF page count
      - image dimensions
      - timeout
      - memory/resource limits where practical

  5. Ensure invalid files are rejected before parser execution.
  6. Keep manual receipt entry working.

  ### Receipt File Authorization

  1. Receipt images/files must require appropriate role and business access.
  2. Add authorization checks to receipt file/image routes.
  3. Avoid leaking file existence through overly specific errors.
  4. Add tests for low-privilege users.

  ## Tests Required

  Add or update tests for:

  - spoofed extension rejected
  - unsupported MIME rejected
  - oversized file rejected
  - valid image/PDF accepted
  - low-privilege user cannot access receipt image
  - admin/staff can access receipt image
  - manual receipt entry still works

  ## Verification

  Run:

  uv run pytest tests -k "receipt or upload"
  uv run ruff check app/services/receipts.py app/blueprints/receipts tests

  ## Deliverable

  Summarize:

  - Upload validation changes
  - Parser safety limits
  - Receipt file authorization changes
  - Tests added

  ———

  # Phase 4: Internal Services, Config, Secrets, and Migrations

  ## Goal

  Remove unsafe service defaults, harden production config, and eliminate destructive migration behavior.

  ## Findings Covered

  - Intelligence service accepts internal token in query string
  - Destructive Alembic migration drops tables during upgrade
  - Production config allows insecure defaults
  - Docs service open by default
  - Docs service .env not ignored

  ## Tasks

  ### Intelligence Service

  1. Remove query-string token authentication.
  2. Require Authorization: Bearer ....
  3. Use constant-time comparison.
  4. Remove unsafe default token behavior where practical.
  5. Add tests.

  ### Migrations

  1. Remove destructive table drops from upgrade migrations.
  2. Convert destructive cleanup into explicit manual scripts or guarded operations.
  3. Add migration safety checks if practical.
  4. Document any migration risk.

  ### Production Config

  1. Fail production startup when critical secrets are missing or default.
  2. Add secure cookie flags.
  3. Add standard security headers:
      - X-Content-Type-Options
      - X-Frame-Options
      - Referrer-Policy
      - Permissions-Policy
      - HSTS when HTTPS/secure cookies are enabled

  4. Add tests for production config validation.

  ### Docs Service

  1. Make docs auth required by default outside development.
  2. Fail startup if docs auth is required but credentials are missing.
  3. Add tests.

  ### Git Ignore

  1. Add services/dfpos-api-docs/.env to .gitignore.

  ## Tests Required

  Add or update tests for:

  - query-string token rejected
  - bearer token accepted
  - production config rejects default secrets
  - security headers present
  - docs auth required when configured
  - destructive migration safety check if implemented

  ## Verification

  Run:

  uv run pytest tests services -k "config or security or docs or intelligence or migration"
  uv run ruff check app services tests

  ## Deliverable

  Summarize:

  - Config hardening
  - Service auth changes
  - Migration safety changes
  - Tests added
  - Required env var updates

  ———

  # Phase 5: Rate Limiting and Abuse Protection

  ## Goal

  Reduce brute-force and abuse risk for login and API token authentication.

  ## Findings Covered

  - No login/API rate limiting or lockout

  ## Tasks

  1. Add Flask-Limiter or the project-preferred limiter.
  2. Rate-limit login POST attempts.
  3. Rate-limit API token authentication failures.
  4. Consider account-based lockout or escalating delay after repeated failures.
  5. Audit lockout or repeated failed auth events where practical.
  6. Update config and .env.example.

  ## Tests Required

  Add or update tests for:

  - repeated login attempts return 429
  - successful login still works
  - API auth failures are limited
  - limits can be configured for testing

  ## Verification

  Run:

  uv run pytest tests -k "auth or login or rate"
  uv run ruff check app/blueprints/auth.py app/utils/auth.py app/config.py tests

  ## Deliverable

  Summarize:

  - Limiter added
  - Config values added
  - Tests added
  - Any production tuning notes

  ———

  # Phase 6: Docker and Deployment Hardening

  ## Goal

  Make the container/deployment path safer and closer to production expectations.

  ## Findings Covered

  - Compose exposes services with defaults
  - Runtime installs/builds assets
  - App runs as root
  - CSS build failure ignored
  - Migrations run during web startup
  - Missing healthcheck behavior

  ## Tasks

  1. Remove default production secrets from compose.
  2. Use ${VAR:?message} for required secrets.
  3. Avoid exposing internal services by default.
  4. Split dev-only exposure into override file if needed.
  5. Avoid runtime npm install.
  6. Avoid runtime asset builds in production startup.
  7. Do not ignore CSS build failures.
  8. Run app as non-root where practical.
  9. Add healthcheck endpoint if missing.
  10. Add Docker healthcheck configuration.
  11. Move migrations to an explicit release/admin command, not web boot, unless clearly documented as dev-only.

  ## Tests/Checks Required

  Run or document:

  docker compose config
  docker compose build web
  npm run build:css

  If Docker cannot run in the environment, explain exactly what should be run.

  ## Deliverable

  Summarize:

  - Dockerfile changes
  - Compose changes
  - Healthcheck behavior
  - Migration startup behavior
  - Required deployment env vars

  ———

  # Phase 7: Playwright and Critical E2E Coverage

  ## Goal

  Add browser-level regression coverage for workflows unit tests cannot fully protect.

  ## Findings Covered

  - Missing Playwright/E2E coverage for critical UI flows

  ## Tasks

  1. Add Playwright dev dependency.
  2. Add npm run test:e2e.
  3. Add stable data-testid attributes where needed.
  4. Add E2E tests for:
      - authenticated POS cash sale
      - POS rejects/prevents tampered client-side price
      - receipt upload/review happy path
      - low-privilege user cannot access receipt image
      - admin critical workflow smoke test

  5. Ensure tests can run against local app.
  6. Document required setup.

  ## Tests Required

  Create Playwright tests under a clear location such as:

  tests/e2e/

  or

  e2e/

  ## Verification

  Run:

  npm run test:e2e

  If the app/server/database cannot be started in the current environment, document the exact commands needed.

  ## Deliverable

  Summarize:

  - Playwright setup
  - E2E tests added
  - Selectors added
  - Any flows still missing browser coverage

  ———

  # Phase 8: Full Regression, Documentation, and Scorecard

  ## Goal

  Finish with clean verification and updated documentation.

  ## Tasks

  1. Run the full available verification suite.
  2. Fix regressions found by tests/checks.
  3. Update TODO.md.
  4. Update or create docs/production_readiness_scorecard.md.
  5. Update .env.example with new required config.
  6. Document Docker/compose changes.
  7. Document migration behavior changes.
  8. Record any intentionally deferred work.

  ## Required Verification

  Run:

  uv run ruff check app services tests
  uv run python -m py_compile app/config.py app/__init__.py
  uv run pytest
  npm run build:css
  npm run test:e2e
  docker compose config

  If any command cannot be run, explain:

  - command attempted
  - failure reason
  - whether it is environment-related or code-related
  - exact next command to run after fixing prerequisites

  ## Final Deliverable

  Report:

  1. Findings fixed, grouped by Critical/High/Medium/Low
  2. Files changed
  3. Tests added or updated
  4. Commands run and results
  5. Remaining risks or deferred items
  6. Required environment variable changes
  7. Docker/deployment changes
  8. How to run the app and verification locally

  Do not stop after planning. Implement each phase, verify it, commmit / push to git and move to the next phase unless a blocker requires user input.


 
