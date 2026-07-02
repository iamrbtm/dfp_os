  You are implementing the DFPos Intelligence microservice for /Users/rbtm2006/Documents/Projects/dfp_os.

  Do not rewrite the main DFPos architecture. DFPos remains a Flask/MariaDB modular monolith and the operational source of truth. Build a separate analytics/
  decision microservice under services/intelligence/ that imports old data, creates an analytics warehouse, and exposes read-only recommendations back to DFPos.

  Read first:
  - AGENTS.md
  - DESIGN.md
  - ARCHITECTURE.md
  - TODO.md
  - docs/production_readiness_scorecard.md
  - docs/Trend Scout Production Roadmap.md if relevant
  - app/module_registry.py
  - existing services for analytics, cost_engine, prep_tasks, markets, pos, orders, receipts, audit_client

  Goal:
  Create a production-minded “DFP Intelligence” service that combines historical Square exports, old MariaDB data, and current DFPos operational snapshots to
  support future market decisions. The LLM must not be the source of truth. SQL/materialized summaries provide exact facts, Python logic provides forecasts/
  recommendations, RAG provides unstructured context, and the LLM explains grounded recommendations.

  Architecture:
  - Add services/intelligence/
  - Use FastAPI, PostgreSQL 17, SQLAlchemy 2.x async, Alembic, Pydantic, pytest
  - Include optional pgvector support for notes/RAG
  - Add Docker Compose service and .env.example entries
  - Use bearer-token internal auth
  - Send audit events to the existing audit-log service where appropriate
  - Do not store secrets
  - Do not commit .env
  - Do not let the service write directly to DFPos operational tables

  Implement in phases, stopping after each phase with tests and a summary.

  Phase 1:
  Scaffold the service with health endpoint, config, DB connection, Alembic, Docker wiring, pytest smoke tests, and README.

  Phase 2:
  Add import-batch models and raw staging tables for Square item CSV exports. Preserve raw rows and import metadata. Validate required columns. Drop or
  quarantine sensitive fields such as card token and PAN suffix. Add tests using small fixture CSVs.

  Phase 3:
  Add old-MariaDB import connector design with read-only credentials, schema inspection, raw table import batches, and clear failure handling. Do not require
  live credentials in tests.

  Phase 4:
  Create normalization/mapping models for historical product/category/SKU/channel/customer aliases. Add match confidence, reviewed status, reviewer, and notes.
  Do not auto-merge low-confidence matches.

  Phase 5:
  Create warehouse fact/dimension tables and materialized summaries for product sales, seasonal performance, channel performance, transaction lines, market
  context, expenses, inventory snapshots, and product margin. Use Decimal/integer cents, not floats.

  Phase 6:
  Add a recommendation engine for Market Advisor:
  - suggested products to bring
  - suggested quantities
  - products to print before market
  - inventory gaps
  - expected revenue range
  - booth-fee/profit risk
  - explanation inputs/evidence
  Recommendations must be deterministic and testable before adding LLM explanations.

  Phase 7:
  Add RAG support for market notes, receipt text, product descriptions, and custom-order notes using pgvector if available. Keep vector search separate from
  exact SQL math.

  Phase 8:
  Add safe “Ask DFP” endpoints that only call allowlisted query/recommendation tools. No arbitrary model-generated SQL execution. Every answer must include
  evidence references.

  Phase 9:
  Integrate DFPos main app:
  - Add module registry entry if appropriate
  - Add settings for intelligence service URL/token
  - Add Flask client service
  - Add admin pages: Data Imports, Data Health, Product Mapping, Market Advisor, Decision Log
  - Add feature flag enforcement
  - Use DESIGN.md tokens and existing admin layout patterns

  Phase 10:
  Add decision log feedback loop:
  - Store recommendation inputs, outputs, evidence, user action, and actual outcome
  - Add comparison after market completion
  - Use this as the future dataset for evaluation/fine-tuning

  Verification:
  - Run targeted pytest for the service
  - Run relevant DFPos tests
  - Run py_compile on changed Python files if full tests are blocked
  - Document limitations and next steps
  - Update TODO.md and docs/production_readiness_scorecard.md if this is part of a readiness pass

  Hard rules:
  - No real card processing data
  - No arbitrary LLM SQL
  - No writes to historical MariaDB
  - No writes from intelligence service directly into DFPos operational records
  - No hallucinated recommendations without evidence
  - Exact numbers must come from SQL summaries
  - LLM output must be optional and disabled gracefully