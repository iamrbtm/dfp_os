# Title: Historical Sales And Market Import Implementation Prompt
  - Context:
      - DFPos is the current Flask/MariaDB app.
      - Square CSVs are authoritative sales history.
      - Legacy MySQL DB is supporting market/product/packing context.
      - Goal is to improve Trend Scout, analytics, market prep, and product demand history.

  - Source inputs:
      - /Users/rbtm2006/Downloads/items-2025-01-01-2026-01-01.csv
      - /Users/rbtm2006/Downloads/items-2024-01-01-2025-01-01.csv
      - /Users/rbtm2006/Downloads/items-2023-01-01-2024-01-01.csv
      - /Users/rbtm2006/Downloads/items-2022-12-01-2023-01-01.csv
      - Legacy DB env vars only, no inline password.

  - Known observed totals to verify:
      - Square CSVs: 4,895 item rows, 3,676 transactions, 6,029 net units, $42,332.25 net sales, 53 refund rows, date range 2022-12-02 to 2025-09-27.
      - Legacy DB: 86 bookings, 2,471 booking-product rows, 110 products, roughly 5,663 sold units, about $41,162 estimated line revenue.

  ## Required Phases

  1. Phase 0: Repo And Data Audit
      - Read AGENTS.md, DESIGN.md, ARCHITECTURE.md, TODO.md.
      - Inspect current models/services for products, markets, POS, orders, payments, internal demand, Trend Scout, analytics.
      - Inspect CSV headers and aggregate counts.
      - Inspect legacy DB schema read-only if credentials are available through env.
      - Produce a short audit note in the doc or TODO.md.
      - Run non-mutating checks only.
      - Commit and push audit/doc changes.

  2. Phase 1: Import Tracking Foundation
      - Add LegacyImportBatch and LegacyImportMap.
      - Add Alembic migration.
      - Add service skeleton under app/services/legacy_import/.
      - Add CLI group under existing Flask CLI patterns.
      - No actual import writes yet except tracking tables.
      - Test migration/model creation.
      - Commit and push.

  3. Phase 2: Square CSV Parser And Dry Run
      - Build robust CSV parser for multiline notes and Square money fields.
      - Group rows by Transaction ID.
      - Parse Payment and Refund event types.
      - Ignore/import-sensitive fields safely: do not store PAN suffix, card token, or unnecessary customer names by default.
      - Add dry-run command that prints counts, totals, unmatched SKUs, refund totals, and date range.
      - Tests for parser, money parsing, refunds, duplicate reruns.
      - Commit and push.

  4. Phase 3: Product And Category Matching
      - Match by SKU first, normalized item name second.
      - Create missing categories/products as needs_review.
      - Preserve aliases for multi-name SKUs through mapping metadata.
      - Do not mark license/commercial status as approved.
      - Add tests for SKU match, alias conflict, blank SKU, unmatched product creation.
      - Commit and push.

  5. Phase 4: Import Square Sales Into DFPos
      - Create historical Order, OrderItem, Payment, PosSale, PosSaleItem, and daily/historical PosSession rows.
      - Use Square date/time as created/completed/payment timestamps.
      - Payments become completed sales.
      - Refund rows become refund/negative adjustments and must not inflate positive demand.
      - Preserve Square transaction/payment IDs and dashboard URL in safe metadata or mapping rows.
      - Dry-run and apply modes must be idempotent.
      - Tests for no duplication, totals matching, refunds, discounts, and POS/order consistency.
      - Commit and push.

  6. Phase 5: Legacy Market Context Import
      - Import legacy bookings as Market records.
      - Import venue/master list fields into market location/event metadata.
      - Import booking_products into MarketPackingList for packed/sold/remaining context.
      - Import booth fees/expenses where cleanly attributable.
      - Do not treat future zero-sale bookings as negative demand.
      - Add market attribution logic for Square sales by event date/date range.
      - Tests for exact match, ambiguous market, no market, future zero-sale rows.
      - Commit and push.

  7. Phase 6: Trend Scout And Analytics Integration
      - Create InternalDemandEvent rows from Square payment item rows only.
      - Use occurred date, product, category, quantity, net sales, source metadata.
      - Update Trend Scout/backtest only if needed so imported history influences product demand metrics.
      - Run Trend Scout/backtest tests and analytics smoke tests.
      - Commit and push.

  8. Phase 7: Final Verification And Documentation
      - Run MariaDB migration checks using Docker MariaDB, not SQLite.
      - Run targeted pytest first, then broader tests if feasible.
      - Add final import runbook to docs.
      - Update TODO.md with completed work and remaining manual reconciliation.
      - Provide final summary with counts imported, unmatched SKUs/products, ambiguous markets, and verification commands.
      - Commit and push final documentation.

  ## Important Defaults

  - Never commit .env, passwords, API keys, CSV files, or raw card/customer-sensitive fields.
  - Use uv for commands.
  - Use current DFPos MariaDB as target.
  - Use Square CSVs as sales truth.
  - Use old DB as market/packing/product context.
  - Every phase ends with git status, targeted verification, git add, git commit, and git push.
  - If tests fail, fix before committing unless documenting a true environment blocker.