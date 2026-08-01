• Finish Task 8 only in /mnt/storage/docker/dfpos. Do not begin Task 9 or
  later.

  Read:
  - AGENTS.md
  - docs/superpowers/plans/2026-07-31-bambu-primary-product-slicing.md
  - .superpowers/sdd/2026-07-31-bambu-primary-product-slicing/progress.md
  - .superpowers/sdd/2026-07-31-bambu-primary-product-slicing/task-8-report.md

  Safety:
  - Preserve all existing changes.
  - Do NOT delete Docker volumes, containers, or database data.
  - Do NOT run docker system prune --volumes.
  - Do not reset/drop databases or perform destructive cleanup.

  Task 8 status:
  - Latest committed Task 8 commit: `41930f0 fix(products): recover stale
  analysis states and nested assets`
  - There are uncommitted Task 8 test edits in:
    - tests/test_model_analysis_publication_recovery.py
    - tests/test_product_asset_routes.py
  - Preserve and complete those edits.

  Finish these final Task 8 fixes:

  1. Add `AnalysisRunStatus.CONVERTING` to `ACTIVE_ANALYSIS_STATES` in `app/
  services/product_analysis.py`.
     - Add tests proving stale CONVERTING runs can be reclaimed.
     - Add tests proving fresh CONVERTING runs cannot be reclaimed.

  2. Protect generated run-scoped assets from deletion.
     - Nested generated assets use names such as:
       `analysis-runs/<numeric-run-id>/dragon.gcode.3mf`
     - Downloads must remain supported.
     - DELETE for any valid `analysis-runs/<numeric-id>/...` asset must return
     HTTP 409 and must not delete storage objects or leave
     `ProductModelAsset` / `ProductAnalysisRun` database pointers dangling.
     - Add route tests for generated GCODE and generated metadata deletion
     denial.
     - Keep traversal, absolute-path, malformed, and foreign-product paths
     rejected.

  3. Review the stale-worker fencing concern:
     - Ensure existing locking/current-run checks prevent an older reclaimed
     worker from publishing over a newer valid result.
     - Only change code if a concrete race remains; keep scope limited to Task
     8.

  Use TDD, then commit only Task 8 production/test changes:

  `fix(products): protect generated analysis artifacts`

  Verification:
  - Run focused non-DB Task 8 tests.
  - Run Ruff check, Ruff format check, `py_compile`, and `git diff --check`.
  - Attempt DB-backed Task 8 tests with a bounded timeout only.
  - Known limitation: DB fixture setup may stall/fail at `db.create_all()` due
  MariaDB/PyMySQL SSL or missing test tables. Capture exact output, but do not
  repair it destructively.
  - Perform one fresh read-only final review of Task 8 after the commit.
  - Update `.superpowers/sdd/2026-07-31-bambu-primary-product-slicing/
  progress.md` only once Task 8 is approved.

  Do not modify Docker, compose, Task 9+, or unrelated files.
