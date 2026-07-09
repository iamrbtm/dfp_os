 ### 1. Summary Table of Findings

   ID         File/Component      Issue Name                            Category        Severity    Short Description
  ━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━  ━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   CRIT-01    app/services/       POS trusts client-side price and      Security/Bug    Critical    Checkout accepts browser-supplied
              pos.py:131, app/    totals                                                            unit_price, discounts, quantities,
              blueprints/pos/                                                                       and tax values for financial
              routes.py:198                                                                         records.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   CRIT-02    docker-             Production-like compose exposes       Security        Critical    MariaDB, Postgres, Redis,
              compose.yml:8       services with default credentials                                 SeaweedFS, audit, intelligence, and
                                                                                                    docs services expose host ports and
                                                                                                    default passwords/tokens.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   CRIT-03    app/services/       Financial actions do not fail         Security/Gap    Critical    Audit failures are logged and
              audit_client.py:    closed when audit dispatch fails                                  swallowed, while POS/refund/
              61, app/                                                                              financial mutations commit.
              config.py:125
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-01    app/models/         API tokens default to full access     Security        High        Empty scopes mean full access; API
              api_token.py:41,    and can mint more tokens                                          token endpoints can create
              app/blueprints/                                                                       unrestricted tokens.
              api/
              routes.py:1677
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-02    app/blueprints/     Generic REST CRUD bypasses domain     Security/Bug    High        API updates can directly mutate
              api/                workflows                                                         receipt status, POS sale status,
              routes.py:592                                                                         and inventory counts without
                                                                                                    approval/refund/movement services.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-03    app/services/       Receipt upload validation is          Security        High        Untrusted files are routed into
              receipts.py:78,     extension-only before native                                      ImageMagick, Poppler, and Tesseract
              app/services/       parser execution                                                  based mostly on filename extension.
              receipt_provider
              s/
              image_preprocess
              or.py:57
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-04    app/blueprints/     Receipt image endpoint lacks role/    Security        High        Any logged-in user can request
              receipts/           ownership enforcement                                             stored receipt images by ID.
              routes.py:578
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-05    services/           Intelligence service accepts          Security        High        Tokens can leak through logs,
              intelligence/       internal token in query string                                    browser history, proxies, and
              app/                                                                                  referrers.
              security.py:8
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-06    services/           Destructive migration drops tables    Bug/Gap         High        Applying an upgrade can destroy
              intelligence/       during upgrade                                                    intelligence-service data.
              alembic/
              versions/0006_ad
              d_missing_intell
              igence_models.py
              :21
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   HIGH-07    app/                Production config allows insecure     Security/Gap    High        App can boot with
              config.py:23,       defaults                                                          SECRET_KEY=change-me, dev default
              app/                                                                                  config, insecure cookies, and no
              __init__.py:43                                                                        standard security headers.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   MED-01     app/blueprints/     Inventory transfer route              Bug             Medium      Ruff flags db as undefined; the
              inventory/          references undefined db                                           route will crash on commit/
              routes.py:324                                                                         rollback.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   MED-02     app/blueprints/     No login/API rate limiting or         Security        Medium      Password guessing and token brute-
              auth/               lockout                                                           force attempts are not throttled.
              routes.py:13,
              app/utils/
              auth.py:42
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   MED-03     services/dfpos-     API docs service is open by           Security        Medium      If docs credentials are unset, auth
              api-docs/app/       default                                                           passes automatically.
              routes.py:65
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   MED-04     Dockerfile:30,      Container/runtime is not              Gap             Medium      Runs as root, bind-mounts source,
              docker-             production-hardened                                               installs/builds at runtime, runs
              compose.yml:51                                                                        migrations on boot, and ignores CSS
                                                                                                    build failure.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   MED-05     package.json:6,     Missing Playwright/E2E coverage       Testing Gap     Medium      POS, receipt review, checkout, and
              tests               for critical UI flows                                             admin mutation flows lack browser
                                                                                                    regression tests.
  ─────────  ──────────────────  ────────────────────────────────────  ──────────────  ──────────  ─────────────────────────────────────
   LOW-01     .gitignore:1,       Docs service local .env is not        Security/Gap    Low         Root .env and other service envs
              services/dfpos-     ignored                                                           are ignored, but docs service .env
              api-docs/.env                                                                         is not explicitly protected.

  ### 2. Detailed Breakdown & Remediation Write-ups

  #### CRIT-01 POS trusts client-side price and totals

  Root Cause Analysis:
  The POS checkout route forwards cart data from the browser into PosService.create_sale. The service then uses client-controlled
  quantity, unit_price, discount_amount, tax_total, item_type, and descriptions when creating orders, payments, inventory deductions,
  and sales. Browser-rendered product tiles include prices, but those values are not authoritative. A user with DevTools or a scripted
  request can submit unit_price=0.01, negative discounts, altered quantities, or inconsistent totals.

  Impact:
  Production sales, payments, revenue analytics, tax totals, inventory depletion, market profitability, and cost-engine reporting can be
  corrupted. A cashier/helper account could intentionally or accidentally sell inventory for the wrong price. Negative or malformed
  values could create refunds/credits without using refund workflows.

  Remediation Steps:

  1. Treat the server database as the source of truth for product prices.
  2. Validate quantity > 0, discount >= 0, tax >= 0, and no negative totals.
  3. Allow custom-item prices only for explicit custom_item / custom_deposit types with server-side bounds.
  4. For cash, require amount_received >= total.
  5. Add tests for tampered prices, negative quantity, and insufficient cash.

  Code Implementation:

  Before:

  quantity = int(item.get("quantity", 1))
  unit_price = Decimal(str(item.get("unit_price", "0")))
  discount_amount = Decimal(str(item.get("discount_amount", "0")))
  line_total = (unit_price * quantity) - discount_amount

  After:

  if quantity <= 0:
      raise ValueError("Quantity must be greater than zero.")

  item_type = item.get("item_type", "product")
  discount_amount = Decimal(str(item.get("discount_amount", "0")))
  if discount_amount < 0:
      raise ValueError("Discount cannot be negative.")

  if item_type == "product":
      product = Product.query.get(item.get("product_id"))
      if not product or product.status != ProductStatus.ACTIVE:
          raise ValueError("Product is not available for sale.")
      unit_price = Decimal(product.base_price or 0).quantize(Decimal("0.01"))
      description = product.name
  else:
      unit_price = Decimal(str(item.get("unit_price", "0"))).quantize(Decimal("0.01"))
      if unit_price < 0:
          raise ValueError("Custom item price cannot be negative.")
      description = item.get("description", "Custom item")

  line_total = (unit_price * quantity) - discount_amount
  if line_total < 0:
      raise ValueError("Line total cannot be negative.")

  if payment_method == "cash" and amount_received < total:
      raise ValueError("Cash received must cover the sale total.")

  Verification:

  def test_pos_rejects_tampered_product_price(client, admin_user, product, pos_session):
      login(client, admin_user)
      response = client.post(
          f"/pos/api/sessions/{pos_session.id}/checkout",
          json={
              "payment_method": "cash",
              "amount_received": "1.00",
              "items": [{
                  "product_id": product.id,
                  "quantity": 1,
                  "unit_price": "0.01",
                  "description": product.name,
              }],
          },
      )
      assert response.status_code == 400

  #### CRIT-02 Production-like compose exposes services with default credentials

  Root Cause Analysis:
  docker-compose.yml contains fallback credentials such as username:password, rootpassword, dfp_audit_password,
  dfp_intelligence_password, change-me-audit-token, and default SeaweedFS keys. It also exposes stateful/internal services on host
  ports: MariaDB, Postgres, Redis, SeaweedFS, audit-log, intelligence, and docs.

  Impact:
  If this compose file or its pattern is used on a reachable host, attackers can access databases, object storage, Redis, internal APIs,
  or service docs using default credentials. Redis exposure is especially dangerous because it often leads to data tampering or remote
  execution chains depending on configuration.

  Remediation Steps:

  1. Remove host port exposure for internal services unless specifically needed.
  2. Require secrets with ${VAR:?message} rather than fallback defaults.
  3. Bind development-only ports to 127.0.0.1.
  4. Split docker-compose.dev.yml from production compose.
  5. Move production secrets to Docker secrets, environment manager, or deployment platform secrets.

  Code Implementation:

  Before:

  environment:
    DATABASE_URL: ${DATABASE_URL:-mysql+pymysql://username:password@db:3306/dudefish_os}
    AUDIT_LOG_TOKEN: ${AUDIT_LOG_TOKEN:-change-me-audit-token}

  db:
    ports:
      - "3306:3306"
    environment:
      MARIADB_PASSWORD: password
      MARIADB_ROOT_PASSWORD: rootpassword

  After:

  environment:
    DATABASE_URL: ${DATABASE_URL:?DATABASE_URL must be set}
    AUDIT_LOG_TOKEN: ${AUDIT_LOG_TOKEN:?AUDIT_LOG_TOKEN must be set}

  db:
    expose:
      - "3306"
    environment:
      MARIADB_PASSWORD: ${MARIADB_PASSWORD:?MARIADB_PASSWORD must be set}
      MARIADB_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD:?MARIADB_ROOT_PASSWORD must be set}

  Verification:

  docker compose config | grep -E "change-me|rootpassword|username:password" && exit 1 || exit 0

  #### CRIT-03 Financial actions do not fail closed when audit dispatch fails

  Root Cause Analysis:
  AuditClient.record() catches requests.RequestException and logs a warning, returning None. Critical POS sale/refund flows commit
  database state and only then dispatch audit events. The config has AUDIT_LOG_FAIL_CLOSED, but the client and financial services do not
  consistently enforce fail-closed behavior.

  Impact:
  A production outage, token mismatch, or network issue in the audit-log service allows financial mutations to succeed without an
  immutable audit trail. This violates the project’s own rule: financial actions should fail closed unless explicitly configured
  otherwise.

  Remediation Steps:

  1. Add an explicit critical=True option to audit dispatch.
  2. Raise an exception when audit dispatch fails and fail-closed is enabled.
  3. For financial workflows, record audit inside the transaction boundary or use a reliable transactional outbox.
  4. Add tests that simulate audit outage for POS sale/refund.

  Code Implementation:

  Before:

  except requests.RequestException as exc:
      current_app.logger.warning("Audit dispatch failed: %s", exc)
      return None

  After:

  class AuditDispatchError(RuntimeError):
      pass

  except requests.RequestException as exc:
      current_app.logger.warning("Audit dispatch failed: %s", exc)
      if critical and current_app.config.get("AUDIT_LOG_FAIL_CLOSED", False):
          raise AuditDispatchError("Critical audit event could not be dispatched") from exc
      return None

  Before:

  db.session.commit()
  self._record_sale_audit(sale)

  After:

  self._record_sale_audit(sale, critical=True)
  db.session.commit()

  Verification:

  def test_pos_sale_fails_closed_when_audit_unavailable(app, monkeypatch):
      app.config["AUDIT_LOG_FAIL_CLOSED"] = True
      monkeypatch.setattr("app.services.audit_client.AuditClient.record", side_effect=AuditDispatchError())
      with pytest.raises(AuditDispatchError):
          pos_service.create_sale(...)

  #### HIGH-01 API tokens default to full access and can mint more tokens

  Root Cause Analysis:
  ApiToken.has_scope() returns True when no scopes are configured. The UI explicitly says leaving all scopes unchecked creates full
  access. The API token resource can create tokens through /api/v1/api-tokens, and if scopes are omitted, the new token is unrestricted.
  Authentication also checks the token’s active state but not whether the owning user is still active.

  Impact:
  A leaked token with empty scopes is effectively superuser API access. A scoped token with settings/API-token access can mint a broader
  token. Deactivated users may retain working API tokens.

  Remediation Steps:

  1. Make empty scopes mean no access, not full access.
  2. Require an explicit admin or all scope for full access.
  3. Deny API token creation through API unless using a narrowly protected admin-only permission.
  4. Revoke or reject tokens when owning users are inactive.
  5. Add a one-time migration to convert legacy empty-scope tokens to explicit full-access tokens only after admin review.

  Code Implementation:

  Before:

  def has_scope(self, scope: str) -> bool:
      scopes = self.scope_set()
      if not scopes:
          return True
      return scope in scopes

  After:

  def has_scope(self, scope: str) -> bool:
      scopes = self.scope_set()
      return "admin" in scopes or scope in scopes

  Before:

  if not token or not token.is_active:
      return None

  After:

  if not token or not token.is_active or not token.user or not token.user.is_active:
      return None

  Verification:

  def test_empty_scope_api_token_has_no_access(api_token):
      api_token.scopes = ""
      assert not api_token.has_scope("products:read")

  #### HIGH-02 Generic REST CRUD bypasses domain workflows

  Root Cause Analysis:
  The generic API update path applies incoming fields directly to models. For receipts, _apply_receipt() allows direct status changes.
  For POS sales, _apply_pos_sale() allows direct status mutation. For inventory records, API updates can directly change quantities
  instead of creating inventory movements.

  Impact:
  Receipts can be marked approved without creating ledger entries. POS sales can be marked refunded/voided without payment and inventory
  corrections. Inventory can be edited without movement history, destroying auditability and analytics.

  Remediation Steps:

  1. Remove workflow fields from generic update schemas.
  2. Add explicit action endpoints: /receipts/<id>/approve, /pos-sales/<id>/refund, /inventory/<id>/adjust.
  3. Route each action through the service layer.
  4. Audit each workflow action with before/after state.
  5. Add tests proving generic PUT cannot mutate protected state.

  Code Implementation:

  Before:

  if "status" in data:
      receipt.status = ReceiptStatus(data["status"])

  After:

  if "status" in data:
      raise ValidationError("Receipt status must be changed through workflow endpoints.")

  Before:

  if "quantity_on_hand" in data:
      record.quantity_on_hand = data["quantity_on_hand"]

  After:

  if "quantity_on_hand" in data or "quantity_reserved" in data:
      raise ValidationError("Inventory quantities must be changed through adjustment endpoints.")

  Verification:

  def test_api_cannot_approve_receipt_with_generic_put(client, receipt, token):
      response = client.put(
          f"/api/v1/receipts/{receipt.id}",
          headers={"Authorization": f"Bearer {token}"},
          json={"status": "approved"},
      )
      assert response.status_code == 400

  #### HIGH-03 Receipt upload validation is extension-only before native parser execution

  Root Cause Analysis:
  Receipt upload validation checks filename extension and size, then routes files into PDF/image/OCR processing. The preprocessor shells
  out to tools such as ImageMagick, Poppler, and Tesseract. These parsers have historically had serious vulnerabilities, and extension-
  only checks are not a security boundary.

  Impact:
  A malicious upload could trigger parser vulnerabilities, resource exhaustion, decompression bombs, or unsafe file handling. Even if no
  RCE exists, large or malformed files can degrade worker availability.

  Remediation Steps:

  1. Validate MIME type using content sniffing, not only filename.
  2. Verify image dimensions/page count before processing.
  3. Enforce parser timeouts, memory limits, and page limits.
  4. Run parsing in an isolated worker/container with reduced privileges.
  5. Consider malware scanning for uploaded files.
  6. Store original files outside web-serving paths.

  Code Implementation:

  Before:

  def _allowed_file(filename: str) -> bool:
      return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_RECEIPT_EXTENSIONS

  After:

  import magic

  ALLOWED_MIME_TYPES = {
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
  }

  def _allowed_file(file_obj, filename: str) -> bool:
      if "." not in filename:
          return False
      ext = filename.rsplit(".", 1)[1].lower()
      if ext not in ALLOWED_RECEIPT_EXTENSIONS:
          return False

      head = file_obj.stream.read(4096)
      file_obj.stream.seek(0)
      detected = magic.from_buffer(head, mime=True)
      return detected in ALLOWED_MIME_TYPES

  Verification:

  def test_receipt_upload_rejects_extension_spoof(client, admin_user):
      login(client, admin_user)
      data = {"receipt_file": (io.BytesIO(b"not a real image"), "fake.png")}
      response = client.post("/receipts/upload", data=data, content_type="multipart/form-data")
      assert response.status_code == 400

  #### HIGH-04 Receipt image endpoint lacks role/ownership enforcement

  Root Cause Analysis:
  The receipt image route is protected by @login_required only. It does not check admin/staff role, ownership, business scope, or
  whether the user is allowed to view sensitive expense documents.

  Impact:
  Any authenticated user can enumerate receipt IDs and access receipt images containing vendor details, payment metadata, addresses, and
  potentially personal information.

  Remediation Steps:

  1. Add role checks to receipt file routes.
  2. Enforce business/account scope.
  3. Return 404 rather than 403 where ID enumeration should be minimized.
  4. Add tests for viewer/helper users.

  Code Implementation:

  Before:

  @bp.route("/receipts/<int:receipt_id>/image")
  @login_required
  def receipt_image(receipt_id: int):
      ...

  After:

  @bp.route("/receipts/<int:receipt_id>/image")
  @login_required
  @roles_required(UserRole.ADMIN, UserRole.STAFF)
  def receipt_image(receipt_id: int):
      ...

  Verification:

  def test_viewer_cannot_access_receipt_image(client, viewer_user, receipt):
      login(client, viewer_user)
      response = client.get(f"/receipts/{receipt.id}/image")
      assert response.status_code in {403, 404}

  #### HIGH-05 Intelligence service accepts internal token in query string

  Root Cause Analysis:
  verify_internal_token() accepts a bearer token from either the Authorization header or a token query parameter. Query parameters are
  commonly logged by proxies, servers, analytics tools, browser history, and monitoring systems.

  Impact:
  Internal service tokens can leak into logs. Once leaked, an attacker can call protected intelligence endpoints if the service is
  reachable.

  Remediation Steps:

  1. Remove query-parameter token support.
  2. Require Authorization: Bearer ....
  3. Use hmac.compare_digest.
  4. Rotate existing intelligence tokens.
  5. Remove host exposure in production compose.

  Code Implementation:

  Before:

  async def verify_internal_token(
      authorization: str | None = Header(default=None),
      token: str | None = Query(default=None),
  ) -> None:
      provided = token
      if authorization and authorization.lower().startswith("bearer "):
          provided = authorization.split(" ", 1)[1].strip()

  After:

  import hmac

  async def verify_internal_token(authorization: str | None = Header(default=None)) -> None:
      if not authorization or not authorization.lower().startswith("bearer "):
          raise HTTPException(status_code=401, detail="Missing bearer token")

      provided = authorization.split(" ", 1)[1].strip()
      expected = settings.internal_api_token
      if not expected or not hmac.compare_digest(provided, expected):
          raise HTTPException(status_code=401, detail="Invalid bearer token")

  Verification:

  def test_query_token_is_rejected(client):
      response = client.get("/api/v1/reviews?token=secret")
      assert response.status_code == 401

  #### HIGH-06 Destructive migration drops tables during upgrade

  Root Cause Analysis:
  The intelligence migration 0006_add_missing_intelligence_models.py drops multiple tables in upgrade(). Migrations should be forward-
  only structural transformations. Dropping production tables during upgrade is destructive and unsafe unless wrapped in an explicit
  manual data-loss procedure.

  Impact:
  Running alembic upgrade head can delete intelligence data in production. This also undermines rollback and disaster-recovery
  expectations.

  Remediation Steps:

  1. Replace destructive drops with additive/alter migrations.
  2. Move destructive cleanup to a manual script requiring an explicit environment confirmation.
  3. Add migration review checks in CI to reject drop_table in upgrades unless allowlisted.
  4. Back up data before any destructive schema operation.

  Code Implementation:

  Before:

  def upgrade() -> None:
      op.drop_table("trend_signal", if_exists=True)
      op.drop_table("trend_snapshot", if_exists=True)

  After:

  def upgrade() -> None:
      # Additive migration only. Do not drop production data in upgrade().
      op.create_table(
          "trend_signal_v2",
          sa.Column("id", sa.Integer(), primary_key=True),
          # ...
      )

  Verification:

  rg "drop_table\\(" services/intelligence/alembic/versions migrations/versions && exit 1 || exit 0

  #### HIGH-07 Production config allows insecure defaults

  Root Cause Analysis:
  The app can boot with SECRET_KEY="change-me" and defaults to development config when FLASK_ENV is absent. Production config does not
  force secure cookies, SameSite, HSTS, CSP, frame protection, or referrer policy.

  Impact:
  Session integrity, CSRF protections, browser-side isolation, and cookie confidentiality are weaker than required for production.
  Misconfigured deployments may silently run with development assumptions.

  Remediation Steps:

  1. Fail startup in production if critical secrets are defaults.
  2. Set secure cookie flags in production.
  3. Add standard security headers.
  4. Use ProxyFix only when deployed behind a trusted proxy.
  5. Add a config test.

  Code Implementation:

  Before:

  SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

  After:

  SECRET_KEY = os.environ["SECRET_KEY"]

  class ProductionConfig(Config):
      SESSION_COOKIE_SECURE = True
      REMEMBER_COOKIE_SECURE = True
      SESSION_COOKIE_SAMESITE = "Lax"
      REMEMBER_COOKIE_SAMESITE = "Lax"

      @classmethod
      def validate(cls) -> None:
          if cls.SECRET_KEY in {"change-me", "change-me-now"}:
              raise RuntimeError("Production SECRET_KEY must be set to a strong secret.")

  Security headers:

  @app.after_request
  def add_security_headers(response):
      response.headers.setdefault("X-Content-Type-Options", "nosniff")
      response.headers.setdefault("X-Frame-Options", "DENY")
      response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
      response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
      if app.config.get("SESSION_COOKIE_SECURE"):
          response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
      return response

  Verification:

  def test_production_rejects_default_secret(monkeypatch):
      monkeypatch.setenv("FLASK_ENV", "production")
      monkeypatch.setenv("SECRET_KEY", "change-me")
      with pytest.raises(RuntimeError):
          create_app()

  #### MED-01 Inventory transfer route references undefined db

  Root Cause Analysis:
  Ruff reports F821 Undefined name db in the inventory transfer route. The route calls db.session.commit() and db.session.rollback() but
  does not import db.

  Impact:
  Inventory transfers can crash at runtime, leaving users unsure whether stock moved. If exceptions occur mid-flow, transaction handling
  is unreliable.

  Remediation Steps:

  1. Import db from app.extensions.
  2. Add a route-level regression test for successful and failed transfers.
  3. Keep inventory state changes in a service method where possible.

  Code Implementation:

  Before:

  from flask import Blueprint, flash, redirect, render_template, request, url_for

  After:

  from flask import Blueprint, flash, redirect, render_template, request, url_for

  from app.extensions import db

  Verification:

  def test_inventory_transfer_does_not_crash(client, admin_user, inventory_record):
      login(client, admin_user)
      response = client.post(f"/inventory/{inventory_record.id}/transfer", data={...})
      assert response.status_code in {302, 200}

  #### MED-02 No login/API rate limiting or lockout

  Root Cause Analysis:
  Login and API token authentication do not have request throttling. A single source can submit repeated passwords or bearer tokens
  without application-level friction.

  Impact:
  Credential stuffing, password guessing, and token brute-force attempts are easier. Audit logging helps visibility but does not prevent
  abuse.

  Remediation Steps:

  1. Add Flask-Limiter.
  2. Rate-limit login by IP and account identifier.
  3. Rate-limit API token failures.
  4. Add temporary account lockout or escalating delay after repeated failures.
  5. Audit lockouts.

  Code Implementation:

  Before:

  @bp.route("/login", methods=["GET", "POST"])
  def login():
      ...

  After:

  @bp.route("/login", methods=["GET", "POST"])
  @limiter.limit("5 per minute", methods=["POST"])
  def login():
      ...

  API token failure limit:

  @limiter.limit("60 per minute")
  def api_token_required(...):
      ...

  Verification:

  def test_login_is_rate_limited(client):
      for _ in range(6):
          response = client.post("/login", data={"email": "admin@example.com", "password": "bad"})
      assert response.status_code == 429

  #### MED-03 API docs service is open by default

  Root Cause Analysis:
  The docs service returns authenticated when DOCS_USERNAME or DOCS_PASSWORD is unset. This is convenient locally but unsafe when
  exposed through compose.

  Impact:
  OpenAPI docs may expose endpoint names, schemas, operational details, and auth patterns to unauthenticated users.

  Remediation Steps:

  1. Require docs auth by default outside development.
  2. Fail startup if docs auth is enabled but credentials are missing.
  3. Disable docs service exposure in production.

  Code Implementation:

  Before:

  if not settings.docs_username or not settings.docs_password:
      return True

  After:

  if settings.docs_auth_required and (not settings.docs_username or not settings.docs_password):
      raise RuntimeError("Docs auth is required but DOCS_USERNAME/DOCS_PASSWORD are missing.")

  Verification:

  def test_docs_requires_auth_when_credentials_missing(monkeypatch):
      monkeypatch.setenv("DOCS_AUTH_REQUIRED", "true")
      monkeypatch.delenv("DOCS_USERNAME", raising=False)
      with pytest.raises(RuntimeError):
          load_settings()

  #### MED-04 Container/runtime is not production-hardened

  Root Cause Analysis:
  The main Dockerfile runs as root, installs Node dependencies during image build, copies the full repo, and ignores CSS build failure
  with || true. Compose bind-mounts the source tree, installs/builds CSS at runtime, and runs database migrations automatically on
  container startup.

  Impact:
  Production containers are mutable, harder to reproduce, and overprivileged. Startup can fail or drift based on network/npm state.
  Automatic migrations during web boot can race across replicas or apply destructive migrations unexpectedly.

  Remediation Steps:

  1. Build assets during image build and fail if build fails.
  2. Run as a non-root user.
  3. Do not bind-mount source in production.
  4. Run migrations as a separate release job.
  5. Add app healthcheck.
  6. Pin image versions instead of latest.

  Code Implementation:

  Before:

  RUN npm run build:css || true
  CMD ["gunicorn", ...]

  After:

  RUN npm ci
  RUN npm run build:css

  RUN useradd --create-home --shell /usr/sbin/nologin appuser
  USER appuser

  CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:create_app()"]

  Compose:

  web:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  Verification:

  docker compose build --no-cache web
  docker compose run --rm web id | grep -v "uid=0"

  #### MED-05 Missing Playwright/E2E coverage for critical UI flows

  Root Cause Analysis:
  The repo has Python tests, but no Playwright dependency or browser E2E suite. The highest-risk flows are UI-heavy and stateful: POS
  checkout, receipt upload/review/approval, public checkout/custom request, inventory adjustment, and market closeout.

  Impact:
  Server unit tests may miss DOM/state bugs, double-submit races, stale CSRF forms, HTMX partial regressions, mobile layout failures,
  and user-visible checkout defects.

  Remediation Steps:

  1. Add Playwright as a dev dependency.
  2. Add E2E smoke tests for authenticated POS sale, receipt review, and admin CRUD.
  3. Use stable data-testid attributes instead of brittle CSS/text selectors.
  4. Run E2E tests in CI against Docker-backed MariaDB.

  Code Implementation:

  Before:

  {
    "scripts": {
      "build:css": "tailwindcss -i ./app/static/src/main.css -o ./app/static/dist/main.css --minify"
    }
  }

  After:

  {
    "scripts": {
      "build:css": "tailwindcss -i ./app/static/src/main.css -o ./app/static/dist/main.css --minify",
      "test:e2e": "playwright test"
    },
    "devDependencies": {
      "@playwright/test": "^1.55.0"
    }
  }

  Verification / Playwright:

  import { test, expect } from "@playwright/test";

  test("cashier can complete a cash POS sale without price tampering", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("change-me-now");
    await page.getByRole("button", { name: /log in/i }).click();

    await page.goto("/pos");
    await page.getByTestId("product-tile").first().click();
    await page.getByTestId("checkout-cash").click();
    await page.getByLabel("Amount received").fill("20.00");
    await page.getByRole("button", { name: /complete sale/i }).click();

    await expect(page.getByText(/sale complete/i)).toBeVisible();
  });

  #### LOW-01 Docs service local .env is not ignored

  Root Cause Analysis:
  The root .gitignore ignores .env, services/audit-log/.env, and services/intelligence/.env, but not services/dfpos-api-docs/.env. A
  local docs .env exists in the working tree.

  Impact:
  A future git add services/dfpos-api-docs/.env could accidentally commit credentials or docs auth secrets.

  Remediation Steps:

  1. Add services/dfpos-api-docs/.env to .gitignore.
  2. Add a secret scanner to CI.
  3. Keep only .env.example tracked.

  Code Implementation:

  Before:

  services/audit-log/.env
  services/intelligence/.env

  After:

  services/audit-log/.env
  services/intelligence/.env
  services/dfpos-api-docs/.env

  Verification:

  git check-ignore services/dfpos-api-docs/.env

  Net assessment: this codebase is not production-ready yet. The largest blockers are financial integrity in POS/API workflows, audit
  fail-closed behavior, insecure deployment defaults, and insufficient hardening around uploads/internal services. The next practical
  move is to fix CRIT-01 through CRIT-03 first, then lock down API workflow mutations and production config before broader QA expansion.

 
