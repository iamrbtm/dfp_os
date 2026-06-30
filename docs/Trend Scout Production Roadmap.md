 # Trend Scout Production Roadmap

  ## Goal

  Turn Trend Scout into a production-grade decision board that answers:

  > What should Dude Fish Printing make, sell, restock, improve, discount, retire, or review next?

  The system should rank current catalog products and potential new products in one sortable matrix using real demand, sales, inventory,
  production, price, local-fit, and license-risk signals.

  ## Current State

  Trend Scout now has the core scoring foundation:

  - Current products and potential products appear in the same opportunity list.
  - Each item gets score components: purchase_intent, trend_velocity, price_resilience, low_saturation, local_fit, production_fit, and
    license_risk.

  - Each item gets a suggested action such as print_now, test_product, clearance_candidate, retire_review, or license_review.
  - Internal demand events, POS sales, online orders, inventory, product metadata, Google Trends, TikTok, and other trend sources can feed the
    score.

  The remaining work is about production reliability, explainability, workflow integration, and decision quality.

  ## Phase 1: Fuzzy Matching And Product-Idea Linking

  ### Objective

  Connect messy trend terms to real catalog products, categories, and product ideas.

  ### Tasks

   Task                          Description                                                               Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Normalize product terms       Expand keyword normalization beyond exact names.                          Shared keyword normalization service
  ────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────────────
   Add fuzzy product matching    Match terms like teacher keychain, custom name tag, and personalized      Product-to-trend match confidence
                                 backpack tag to related products.
  ────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────────────
   Add synonym mapping           Support business-specific synonyms like name sign, desk sign, teacher     Editable synonym list
                                 gift, market display, qr sign.
  ────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────────────
   Match by category and tags    Use product category, collection, tags, and descriptions, not just        Broader product linkage
                                 product name.
  ────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────────────
   Store match confidence        Track whether a match is exact, fuzzy, synonym, category-based, or        Explainable match metadata
                                 weak.
  ────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────────────
   Add tests                     Verify obvious matches, weak matches, and false-positive prevention.      Focused test coverage

  ### Definition Of Done

  Trend Scout can confidently connect potential demand terms to existing products without relying on exact product-name matches.

  ## Phase 2: Score Explainability

  ### Objective

  Make every score auditable and understandable.

  ### Tasks

   Task                            Description                                                                     Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Add score breakdown metadata    Store raw inputs behind each score.                                             Per-score explanation object
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain purchase intent         Show internal searches, carts, orders, POS units, custom requests, revenue,     Purchase-intent explanation
                                   and source weighting.
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain trend velocity          Show week-over-week movement and source changes.                                Velocity explanation
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain price resilience        Show price, estimated profit, margin, and external observed prices.             Price explanation
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain low saturation          Show maker-platform density, repeated listings, and source spread.              Saturation explanation
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain local fit               Show matched local/business terms like Clarksville, Tennessee, teacher,         Local-fit explanation
                                   military-family-safe, vendor, small business.
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain production fit          Show print time, profit, product readiness, POS visibility, and inventory       Production explanation
                                   state.
  ──────────────────────────────  ──────────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Explain license risk            Show license status, commercial-use flag, risky keyword matches, and review     License explanation
                                   reason.

  ### Definition Of Done

  A user can click or expand any row and understand why the system recommended that product or idea.

  ## Phase 3: Persisted Opportunity Score History

  ### Objective

  Move Trend Scout from report-only JSON to durable historical scoring.

  ### Tasks

   Task                           Description                                               Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Add score table                Create a trend_opportunity_scores table.                  Persistent opportunity rows
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Store report linkage           Link each score row to a Trend Report / pipeline run.     Historical run tracking
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Store candidate identity       Track current product ID or potential-product keyword.    Stable candidate identity
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Store score components         Persist all seven score fields and final score.           Queryable scoring history
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Store action recommendation    Persist recommended action and reason metadata.           Historical recommendations
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Store source health            Track which sources contributed to each score.            Data-quality context
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Add migrations                 Create production-safe schema migration.                  Alembic migration
  ─────────────────────────────  ────────────────────────────────────────────────────────  ─────────────────────────────
   Add tests                      Verify score persistence and report linkage.              Persistence tests

  ### Definition Of Done

  Trend Scout can show score history, rank movement, and “why did this change?” over time.

  ## Phase 4: Configurable Scoring Weights

  ### Objective

  Make scoring tunable without code changes.

  ### Tasks

   Task                           Description                                                             Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Move weights into config       Store scoring weights in settings or database-backed config.            Configurable scoring model
  ─────────────────────────────  ──────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add default scoring profile    Seed sensible defaults for Dude Fish Printing.                          Default profile
  ─────────────────────────────  ──────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add admin editor               Let admins adjust source weights and score weights.                     Admin settings UI
  ─────────────────────────────  ──────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add validation                 Prevent invalid weights, negative totals, or broken scoring configs.    Safe config handling
  ─────────────────────────────  ──────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add versioning                 Store scoring version used for each report.                             Reproducible scores
  ─────────────────────────────  ──────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add tests                      Verify defaults, overrides, and invalid config handling.                Config tests

  ### Definition Of Done

  The business can tune scoring priorities such as local fit, purchase intent, production fit, or license risk without editing Python code.

  ## Phase 5: Action Workflow Integration

  ### Objective

  Turn recommendations into work inside DFPos.

  ### Tasks

   Task                        Description                                                         Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━
   Add action buttons          Add row-level actions in the Trend Scout table.                     Actionable UI
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Create print task           Send print_now items into print jobs or prep tasks.                 Production workflow
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Add to market prep          Add recommended products to market prep or packing suggestions.     Market workflow
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Create product idea         Convert potential product into a draft product or idea record.      Product pipeline
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Mark clearance candidate    Flag existing products for discount/clearance review.               Clearance workflow
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Mark retire review          Flag products for removal/retirement review.                        Retire workflow
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Create license review       Send risky products to license/compliance review.                   Compliance workflow
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Audit actions               Log user-triggered actions through audit logging.                   Audit trail
  ──────────────────────────  ──────────────────────────────────────────────────────────────────  ─────────────────────
   Add tests                   Verify each action creates the expected record or status change.    Workflow tests

  ### Definition Of Done

  Trend Scout is no longer just a report; it becomes a command center for product decisions.

  ## Phase 6: Stronger Current-Product Analytics

  ### Objective

  Improve decisions for products already in the store.

  ### Tasks

   Task                           Description                                                                   Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━
   Add sell-through rate          Compare units sold to inventory available.                                    Sell-through score
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add inventory age              Identify products sitting too long.                                           Inventory aging signal
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add days since last sale       Detect stale products.                                                        Last-sale signal
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add stockout detection         Detect products that score low only because they were unavailable.            Stockout-aware scoring
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add market vs online split     Score products differently for vendor markets and online storefront.          Channel-aware scoring
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add margin strength            Use cost engine data more directly.                                           Profit-aware ranking
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add production capacity fit    Consider print time and current queue pressure.                               Capacity-aware score
  ─────────────────────────────  ────────────────────────────────────────────────────────────────────────────  ────────────────────────
   Add tests                      Cover stockout, stale inventory, strong sellers, and high-margin products.    Analytics tests

  ### Definition Of Done

  Recommendations like print_now, clearance_candidate, and retire_review are based on real operating conditions, not just trend popularity.

  ## Phase 7: Source Health And Data Quality Dashboard

  ### Objective

  Make data reliability visible.

  ### Tasks

   Task                         Description                                                                          Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Track source status          Store success, failure, empty result, not configured, timeout, and rate-limit        Source health records
                                states.
  ───────────────────────────  ───────────────────────────────────────────────────────────────────────────────────  ────────────────────────────
   Show source health UI        Display source status on Trend Scout page.                                           Admin visibility
  ───────────────────────────  ───────────────────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add stale-data warnings      Warn when a score is based on old or partial data.                                   Data freshness indicator
  ───────────────────────────  ───────────────────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add provider setup status    Show whether Google, TikTok, Etsy, Pinterest, etc. are configured.                   Setup checklist
  ───────────────────────────  ───────────────────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add retry-safe errors        Make failures visible but non-fatal.                                                 Reliable pipeline behavior
  ───────────────────────────  ───────────────────────────────────────────────────────────────────────────────────  ────────────────────────────
   Add tests                    Verify failure states do not pollute scores.                                         Source health tests

  ### Definition Of Done

  A weak score can be trusted because the user knows whether it came from low demand or missing data.

  ## Phase 8: Backtesting And Score Calibration

  ### Objective

  Prove the scoring model works against actual business results.

  ### Tasks

   Task                          Description                                                           Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━
   Add historical comparison     Compare past scores to later sales and demand events.                 Backtest report
  ────────────────────────────  ────────────────────────────────────────────────────────────────────  ──────────────────────────
   Measure prediction quality    Track whether high-scoring items sold, got searched, or converted.    Accuracy metrics
  ────────────────────────────  ────────────────────────────────────────────────────────────────────  ──────────────────────────
   Identify bad signals          Detect sources or metrics that overpredict weak products.             Calibration notes
  ────────────────────────────  ────────────────────────────────────────────────────────────────────  ──────────────────────────
   Tune weights                  Adjust scoring based on real outcomes.                                Improved scoring profile
  ────────────────────────────  ────────────────────────────────────────────────────────────────────  ──────────────────────────
   Add calibration report        Show which score components are most predictive.                      Admin insight
  ────────────────────────────  ────────────────────────────────────────────────────────────────────  ──────────────────────────
   Add tests                     Verify backtest calculations.                                         Backtest tests

  ### Definition Of Done

  The matrix becomes evidence-calibrated instead of just logically designed.

  ## Phase 9: Admin UX And Sorting

  ### Objective

  Make the Trend Scout page fast enough for real daily use.

  ### Tasks

   Task                      Description                                                                                Output
  ━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━
   Add filters               Filter by action, current product, potential product, source, license risk, inventory      Usable matrix
                             state.
  ────────────────────────  ─────────────────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add sorting               Sort by score, intent, velocity, price, production fit, license risk, inventory.           Decision-table behavior
  ────────────────────────  ─────────────────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add row detail view       Expand each row for explanation and source detail.                                         Drilldown UX
  ────────────────────────  ─────────────────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add saved views           Add views like Print Now, Clearance, License Review, Product Ideas.                        Operational workflow
  ────────────────────────  ─────────────────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add empty/error states    Handle no data, missing sources, and failed runs clearly.                                  Production UX
  ────────────────────────  ─────────────────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add responsive layout     Make the table usable on laptop/tablet.                                                    Better field usability

  ### Definition Of Done

  The page becomes a practical operating screen, not just a report display.

  ## Phase 10: Compliance And Risk Guardrails

  ### Objective

  Prevent risky products from being recommended for sale without review.

  ### Tasks

   Task                                Description                                                                      Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━
   Expand restricted term detection    Add known trademark, character, sports, university, military-logo, and brand     Stronger risk detection
                                       risk terms.
  ──────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add risk reason codes               Store why something was flagged.                                                 Explainable compliance
  ──────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add hard recommendation block       Prevent print_now or test_product when license risk is too high.                 Safer actions
  ──────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add manual override                 Allow admin-reviewed overrides with notes.                                       Controlled override
  ──────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add license-review queue            Centralize risky products and ideas.                                             Review workflow
  ──────────────────────────────────  ───────────────────────────────────────────────────────────────────────────────  ─────────────────────────
   Add tests                           Verify risky terms cannot produce unsafe recommendations.                        Compliance tests

  ### Definition Of Done

  Trend Scout can discover demand without encouraging unsafe or unlicensed products.

  ## Phase 11: Production Verification

  ### Objective

  Verify the feature under the real DFPos runtime expectations.

  ### Tasks

   Task                              Description                                                               Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━
   Run MariaDB migrations            Verify new schema against Docker MariaDB.                                 Migration confidence
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Run targeted tests                Run Trend Scout, internal demand, product, inventory, POS/order tests.    Regression coverage
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Run full suite where practical    Confirm no unrelated breakage.                                            Release confidence
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Test empty states                 Verify no-source, no-product, no-inventory, and no-sales scenarios.       Edge-case confidence
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Test seeded/demo data             Confirm demo flow shows useful matrix rows.                               Usable demo
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Test Celery pipeline              Confirm scheduled/background Trend Scout still works.                     Runtime confidence
  ────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────
   Document setup                    Document Google/TikTok/env setup and fallback behavior.                   Operational docs

  ### Definition Of Done

  Trend Scout works in the real app environment, not only isolated unit tests.

  ## Phase 12: Product Studio Score Button

  ### Objective

  Add a button inside Product Studio that calculates the Trend Scout opportunity score for the current product on demand.

  This lets the user evaluate a product while editing it, without needing to leave Product Studio and manually search the Trend Scout dashboard.

  ### Tasks

   Task                                  Description                                                               Output
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Add “Calculate Trend Score” button    Add a Product Studio action button for the current product.               Product-level scoring action
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Reuse matrix scorer                   Use the same scoring logic as Trend Scout: purchase intent, velocity,     Consistent score calculation
                                         price resilience, low saturation, local fit, production fit, license
                                         risk.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Use latest trend snapshots            Pull the latest available Trend Scout snapshots instead of triggering     Fast on-demand score
                                         a full scrape every time.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Include current product data          Use product price, profit, print time, license status, tags, category,    Product-specific score
                                         inventory, orders, POS sales, and internal demand.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Show score breakdown                  Display the seven score components directly in Product Studio.            Explainable product score
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Show recommendation                   Display action recommendation: print now, keep selling, improve,          Product decision guidance
                                         clearance candidate, retire review, license review, etc.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Add “View In Trend Scout” link        Link from Product Studio to the broader Trend Scout matrix.               Cross-module navigation
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Persist optional score snapshot       Store the calculated score if persistence exists from Phase 3.            Product score history
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Add loading/error states              Handle no trend data, missing product data, and source failures           Production UX
                                         cleanly.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Add audit event                       Record trend_opportunity_score.calculated if the score is persisted or    Audit trail
                                         used to trigger workflow actions.
  ────────────────────────────────────  ────────────────────────────────────────────────────────────────────────  ──────────────────────────────
   Add tests                             Verify the button endpoint calculates the same score as Trend Scout       Regression coverage
                                         and handles missing data.

  ### Definition Of Done

  A user can open any product in Product Studio, click “Calculate Trend Score,” and immediately see:

  - Final opportunity score
  - Purchase intent
  - Trend velocity
  - Price resilience
  - Low saturation
  - Local fit
  - Production fit
  - License risk
  - Recommended action
  - Explanation of the main reasons behind the score

  ### Important Behavior

  The button should not run the full external Trend Scout pipeline by default.

  It should calculate from:

  - Existing product data
  - Existing inventory/order/POS/internal demand data
  - Latest stored trend snapshots
  - Latest stored opportunity-score history if available

  ## Recommended Build Order

  1. Phase 1: Fuzzy matching and product-idea linking.
  2. Phase 2: Score explainability.
  3. Phase 3: Persisted opportunity score history.
  4. Phase 5: Action workflow integration.
  5. Phase 6: Stronger current-product analytics.
  6. Phase 7: Source health dashboard.
  7. Phase 4: Configurable scoring weights.
  8. Phase 8: Backtesting and calibration.
  9. Phase 9: Admin UX and sorting.
  10. Phase 10: Compliance guardrails.
  11. Phase 11: Production verification.
  12. Phase 12: Product Studio Score Button

  ## Practical Milestones

  ### Milestone A: Trust The Scores

  Includes Phases 1, 2, 3, 12, and 7.

  Result: The system gives explainable, persistent, source-aware recommendations.

  ### Milestone B: Act On The Scores

  Includes Phases 5, 6, and 9.

  Result: The system becomes a working product decision board.

  ### Milestone C: Improve The Scores

  Includes Phases 4 and 8.

  Result: The scoring model can be tuned and proven against real sales outcomes.

  ### Milestone D: Ship Safely

  Includes Phases 10 and 11.

  Result: The feature is safer, tested, documented, and production-ready.

  ## Highest-Value Next Phase

  Start with Phase 1 and Phase 2 together.

  Reason: fuzzy matching makes the list accurate, and explainability makes the scores trustworthy. Without those, action workflows could push
  the wrong products into production.