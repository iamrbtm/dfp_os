# Product Flow Gap Remediation Prompt

You are an autonomous senior engineering agent working in the DFPos Flask codebase. Your job is to make the Product Studio product-creation, model-upload, analysis, and costing flow production-grade end to end. Do not stop at partial fixes. Fix the full workflow, add tests, update docs, run verification, and leave the app in a coherent state.

## Required Context

Read these first:

- `AGENTS.md`
- `DESIGN.md`
- `ARCHITECTURE.md`
- `docs/product_creation_developer_flow.md`
- `app/blueprints/products/studio_routes.py`
- `app/forms/studio.py`
- `app/templates/products/studio.html`
- `app/static/src/js/studio.js`
- `app/models/catalog.py`
- `app/models/cost_snapshot.py`
- `app/models/product_ops.py`
- `app/models/inventory.py`
- `app/tasks/model_analysis.py`
- `app/tasks/cost_calculation.py`
- `app/services/model_analysis.py`
- `app/services/model_asset_metadata.py`
- `app/services/cost_engine.py`
- `app/services/storage.py`
- Existing tests under `tests/`

Use the smallest correct architecture, but do not avoid schema changes if they are required for correctness. This is a fresh rebuild, so clean schema improvements are allowed when documented.

## Mission

Make the product flow reliable enough that a staff/admin user can:

1. Create a new product without silent validation failures.
2. Never accidentally publish or activate an incomplete product.
3. Upload a supported quoteable 3D model.
4. See accurate progress and failure states.
5. Get filament grams and print time that match the chosen slicing settings.
6. Get costing that uses the right material/business/spool assumptions.
7. Trust that cost snapshots match the exact analyzed model/version.
8. Re-upload or re-analyze without stale background tasks corrupting the product.
9. See and recover from errors without hidden partial writes.
10. Have tests proving all of the above.

## Critical Bugs To Fix

### 1. Launch Gate Failure Currently Can Persist Blocked Edits

Problem:

- In `studio_routes.studio`, edit mode calls `form.populate_product(product)` before `launch_gate(product)`.
- If launch gate blocks the change, the route returns `_render_studio(product, form, mode, 400)`.
- `_render_studio` calls product ops/default sync and commits.
- Result: blocked active/public/product changes can still be committed without `update_admin_resource` or audit.

Required fix:

- Ensure blocked launch attempts never commit product changes.
- Either validate against a staged copy before mutating the persistent object, or call `db.session.rollback()` before rendering the failure response and reload the product cleanly.
- Remove unsafe commits from `_render_studio` if possible. Rendering should not have surprising product-write side effects.
- If checklist/photo defaults must be created on render, isolate that write so it cannot commit unrelated dirty product fields.

Tests required:

- Attempt to edit a product to `active` or `is_public=True` with missing critical readiness items.
- Assert response is blocked.
- Assert the product remains unchanged in the database.
- Assert no `product.updated` audit event is recorded for the blocked edit.

### 2. Create Flow Bypasses Launch Gate

Problem:

- New products can be created as active/public/POS-visible without readiness checks.
- Launch gate only runs in edit mode.

Required fix:

- Apply launch/readiness gating during creation if the submitted product is active or public.
- Safer default: force new products to draft unless all critical launch checks pass or an explicit override reason is supplied.
- Make the UI clear that products begin as draft until model/cost/license/photo readiness is complete.

Tests required:

- Creating a product as active/public with missing price/license/model should fail or be forced to draft according to the chosen design.
- Creating a complete product with valid override reason should behave predictably and audit the override.

### 3. Validation Errors Are Silent Or Hard To See

Problem:

- `ProductStudioForm` validation failures return the template without clear field errors.
- The route often returns HTTP 200 on invalid POST.
- The template does not render `form.errors` next to fields.

Required fix:

- Render field-level errors for all product fields and upload-modal fields.
- Return HTTP 400 for invalid POSTs.
- Add an error summary at the top of the form.
- Preserve user input after validation failure.
- Make category-empty state actionable with a link to create/manage categories.

Tests required:

- Invalid product POST returns 400.
- Field error text appears in the response.
- Duplicate slug/SKU errors appear before database integrity errors where possible.

### 4. Celery Queue Failures Produce Partial Success Or 500s

Problem:

- `_get_celery()` always imports a Celery object, so the `if celery is not None` branch is effectively always true.
- `.delay()` can fail if Redis/Celery is unavailable after the upload already committed the model as `pending`.
- Browser can show upload failure even though the file was saved.

Required fix:

- Add explicit background-worker availability handling.
- Wrap task enqueue calls in exception handling.
- On queue failure, mark analysis status as `queued_failed` or `failed`, store a friendly error, audit it, and return a clear JSON response.
- Provide a safe synchronous analysis option only if it is intentionally enabled for development/tests, not by accident in production.
- Make cost calculation enqueue failures similarly clear and recoverable.

Tests required:

- Simulate Celery `.delay()` failure for model upload.
- Assert upload route returns controlled JSON and product status is not left as misleading `pending`.
- Simulate cost-task queue failure and assert UI/API response is controlled.

### 5. Failed Analysis Tasks Look Successful To The Browser

Problem:

- `analyze_product_model` returns `{"success": False}` for validation/slicing failures without raising, so Celery state is `SUCCESS`.
- `studio.js` treats any task `SUCCESS` as complete and displays `Model analysis complete`.

Required fix:

- Update `studio.js` to inspect `result.success`.
- If `success === false`, show a failure message, keep/reveal the error, and do not say analysis completed.
- Consider returning a consistent task result envelope for analysis, conversion, cost, and PMP.
- Ensure `analysis-result` includes enough error details for the UI.

Tests required:

- JavaScript behavior should be covered where practical, or backend/task result contract tests should prove failed tasks return a consistent envelope.
- Add a Flask route/task-status test if available.

### 6. Background Analysis Is Race-Prone Across Re-uploads

Problem:

- Product analysis state is stored directly on the `Product` row.
- If a user uploads model A, then uploads model B before model A finishes, model A's task can overwrite product fields for model B.
- Cost snapshots do not store enough model version/hash context to prove what file they belong to.

Required fix:

- Introduce an analysis request/version token, model asset row, or analysis run row.
- Recommended clean approach:
  - Add `ProductModelAsset` or `ProductAnalysisRun` table with product ID, storage reference, original filename, file hash, settings JSON, status, parsed geometry, parsed filament/time, gcode path, converted path, metadata path, error, requested_by, requested_at, completed_at.
  - Keep `Product` summary fields for fast display, but only update them from the latest active analysis run.
  - Pass analysis run ID and expected file reference to Celery tasks.
  - Before writing results, the task must verify the run is still current for the product.
  - Older tasks must finish as stale/superseded without overwriting current product fields.
- If you choose not to add a new table, add a robust `analysis_request_id`/file hash field and enforce it everywhere.

Tests required:

- Start two analysis runs for the same product.
- Complete the older run after the newer run exists.
- Assert older run cannot overwrite current product fields or current cost snapshot.
- Assert stale/superseded status is visible and audited.

### 7. Re-upload Leaves Old Assets And Ambiguous State

Problem:

- Uploading a new model changes `product.model_file_path` but does not archive/delete/mark previous model assets.
- Asset listing can show multiple old models without clear current/stale labels.
- Metadata files may outlive the model version they describe.

Required fix:

- Track active/current model asset explicitly.
- In the Assets modal, label current source model, current G-code, current GLB preview, stale assets, and metadata files.
- Decide and implement retention policy: archive old assets, keep as history, or delete after confirmation.
- Never leave old files indistinguishable from current files.

Tests required:

- Upload/re-upload creates clear current/stale asset state.
- Deleting a current asset safely resets product analysis fields or blocks delete with confirmation.
- Deleting stale assets does not damage current analysis.

## Slicing And Analysis Accuracy Fixes

### 8. Supported File Types Are Misleading

Problem:

- Upload form accepts `stl`, `glb`, `gltf`, `3mf`, and `obj`.
- PrusaSlicer cannot reliably quote every accepted preview format.
- A GLB/GLTF can be accepted by the UI but fail slicing.

Required fix:

- Split supported files into quoteable model formats and preview/reference-only formats.
- Quoteable formats should be only the formats actually supported by the slicer path after verification.
- If GLB/GLTF remain accepted, mark them preview-only and do not claim filament/time analysis will work.
- UI copy and server validation must match.

Tests required:

- Unsupported quoteable format returns a clear validation message.
- Preview-only upload does not start a slicing task unless conversion/slicing support exists.

### 9. Upload Settings Are Stored But Not Fully Honored

Problem:

- `copies`, `scale_percent`, `preserve_orientation`, `multicolor`, `nozzle_diameter`, material, and some printer settings are stored but not fully passed to PrusaSlicer or applied to geometry.
- UI implies these settings affect quoting.

Required fix:

- For every setting shown in the modal, either implement it in slicing/costing or remove/disable it with clear copy.
- Implement scale so geometry, printer-fit checks, slicing, filament grams, and time all reflect selected scale.
- Implement copies semantics clearly:
  - If costing is per single sellable unit, duplicate/arrange copies in the slicer and divide plate material/time by copies only when that is the intended meaning.
  - If costing is per plate/batch, label the output as plate/batch cost and store item count separately.
- Implement or remove `preserve_orientation`.
- Implement or remove `multicolor / wipe tower`.
- Pass nozzle/material/profile settings correctly according to verified PrusaSlicer CLI support.
- Validate embedded 3MF settings after extraction before they can override form settings.

Tests required:

- Unit tests prove scale changes parsed geometry and/or slicer command inputs.
- Unit tests prove copies behavior produces the intended per-unit or per-plate result.
- Command-builder tests prove every visible setting is either honored or intentionally ignored with a documented reason.

### 10. Material Density And Material Type Are Not Reliable

Problem:

- Selecting PETG/ABS/ASA/TPU does not automatically update density.
- Embedded 3MF material can change `material` without changing density.
- Volume-to-grams fallback can use PLA density for non-PLA materials.

Required fix:

- Centralize material definitions with default densities.
- When material changes, density should default appropriately unless the user explicitly overrides it.
- Embedded material settings should map to known density defaults when no explicit density is embedded.
- Persist whether density was defaulted, embedded, or manually overridden.

Tests required:

- PETG/ABS/ASA/TPU defaults are applied correctly.
- Embedded 3MF material updates density correctly.
- Manual density override wins over defaults.

### 11. Geometry Validation May Fail Or Misreport Scene-Based Files

Problem:

- `trimesh.load_mesh` can return scene-like data for multi-mesh formats.
- Current validation assumes mesh properties such as volume, area, faces, and bounds are directly available.

Required fix:

- Normalize loaded geometry into a combined mesh or handle scenes explicitly.
- Record validation warnings instead of failing avoidably.
- Store dimensions after scale is applied.
- Keep raw dimensions and scaled dimensions if useful.

Tests required:

- Multi-mesh/scene validation path is covered with a mocked or small fixture input.
- Scale warning behavior remains tested.

### 12. G-code Parsing Coverage Is Too Narrow

Problem:

- Parser currently recognizes a limited set of Prusa-style comments.
- Bambu/Orca/Prusa variants may emit different names for filament used and time.

Required fix:

- Expand parsing patterns based on real Prusa/Orca/Bambu G-code formats used by the app.
- Preserve source evidence: store which line/pattern supplied grams/time.
- If multiple values exist, choose deterministically and record why.

Tests required:

- Add parser fixtures for Prusa, Orca, and Bambu-style output.
- Include grams, cm3 fallback, days/hours/minutes/seconds, and missing-field failure cases.

## Costing Fixes

### 13. Filament Cost Uses All Spools Instead Of Matching The Product/Material

Problem:

- `_best_spool_match()` averages all spools with remaining grams and cost per gram.
- It does not filter by business, material, color, intended spool, or product settings.
- Snapshot `filament_spool_id` is the most recently updated spool, not necessarily the cost basis.

Required fix:

- Replace `_best_spool_match()` with an explicit material-cost resolver.
- Resolver inputs should include business ID, material type, optional color/spool ID, product/model settings, and fallback policy.
- At minimum, filter by `business_id` and material type.
- If no exact spool match exists, use a clearly labeled fallback with low confidence and warnings.
- Store cost source details in the snapshot: matched spools, weighted average, fallback reason, material type, color if available.

Tests required:

- Multiple businesses' spools cannot affect each other.
- PLA product does not use PETG spool costs.
- Fallback no-spool behavior is explicit and low-confidence.

### 14. Product Studio Missing Cost Inputs

Problem:

- Cost Engine uses labor minutes, labor rate, packaging, payment fees, market allocation, target margin, and failure rate.
- Product Studio only exposes base price and model settings.
- `estimated_labor_minutes` exists on `Product` but is not editable in Product Studio.

Required fix:

- Add a clear Cost Inputs section to Product Studio.
- Include at least labor minutes, optional packaging override, optional target margin override, and optional material/spool selection if available.
- Decide whether fields live on `Product`, `CostSnapshot` inputs, settings, or a dedicated cost profile.
- Keep global defaults visible so users understand what is being assumed.

Tests required:

- Saving cost inputs persists them correctly.
- Cost calculation uses them.
- UI renders defaults and saved values.

### 15. Cost Snapshots Are Not Strong Enough As Evidence

Problem:

- Snapshot inputs do not include model file reference, file hash, analysis run ID, slicer settings, material selection, or density source.
- Snapshot can be recalculated later from changed settings and no longer match what the user saw.
- There is no database guarantee of only one current snapshot.

Required fix:

- Snapshot must reference analysis run/model asset and exact settings used.
- Store file hash, model storage reference, slicer profile, material, density, scale, copies, parsed grams/time, and cost resolver evidence.
- Enforce one current non-stale snapshot per product, either through transaction logic or a database constraint where supported.
- Make stale/current snapshot state deterministic under concurrent calculations.

Tests required:

- Snapshot evidence includes model/version/settings.
- Concurrent or repeated snapshot creation leaves only one current snapshot.
- Old snapshots become stale when a newer one is persisted.

### 16. Manual Calculate Cost Can Produce Misleading No-Model Results

Problem:

- If analysis is pending/failed/missing, `Calculate Cost` can return `no_model` with zero material/machine cost while still rendering normal cost cards.

Required fix:

- UI must clearly distinguish no-model/low-confidence cost estimates.
- Consider blocking product cost calculation until analysis is complete unless the user explicitly requests a manual/no-model estimate.
- Display evidence source and confidence in the cost cards.

Tests required:

- Pending analysis returns a warning state.
- No-model calculation cannot silently look like a normal successful cost.

### 17. Manual Cost Calculation Lacks Audit Coverage

Problem:

- Manual cost calculation persists product estimates and snapshots but does not clearly audit `cost_snapshot.created` or `product_cost.calculated`.

Required fix:

- Audit model-analysis automatic cost snapshots and manual cost recalculations with before/after states and snapshot IDs.
- Include actor where available.

Tests required:

- Manual cost calculation dispatches audit event.
- Automatic model-analysis snapshot dispatches audit event.

## UI And UX Fixes

### 18. Product Studio AJAX Updates Do Not Refresh Readiness

Problem:

- After analysis/costing completes, only metric cards update.
- Readiness score/checklist can remain stale until full page reload.

Required fix:

- Either reload the page after successful analysis/costing or return/render updated readiness/checklist partials.
- Prefer minimal robust behavior: after successful analysis and optional conversion, reload or provide a clear `Refresh` action.

Tests required:

- After analysis success, readiness reflects model analyzed and cost snapshot state.

### 19. Progress State Needs A Real State Machine

Problem:

- Browser progress treats different task states inconsistently.
- Failed validation can look complete.
- Timeout says task may still be running but offers no recovery.

Required fix:

- Standardize task statuses: queued, started, validating, slicing, storing_gcode, costing, converting, complete, failed, superseded.
- Use consistent JSON envelopes for `task-status`, `analysis-result`, `cost-result`.
- Show retry/reanalyze actions on failure.
- Show stale/superseded status on old analysis runs.

Tests required:

- Backend status envelope tests.
- Browser behavior tests if the project has JS testing; otherwise document manual QA steps.

### 20. Upload Size Limits Conflict

Problem:

- UI/form says model files up to 256 MB.
- `ProductModelUploadForm` allows 256 MB.
- Flask `MAX_CONTENT_LENGTH_MB` defaults to 16 MB.

Required fix:

- Add a product/model-specific upload limit config or align global limit to the form/UI.
- Server, form, UI copy, and `.env.example` must agree.
- Handle request-too-large errors with a friendly JSON or page error.

Tests required:

- Oversized uploads return clear 413/400 behavior.
- UI copy reflects actual configured limit.

### 21. Uploads Read Large Files Into Memory

Problem:

- `upload_model` calls `file.read()` for up to 256 MB.
- Metadata hashing also works on full bytes.

Required fix:

- Stream uploads to local/S3 storage where practical.
- Compute hash while streaming.
- Avoid duplicate full-file memory copies.

Tests required:

- Unit test or integration test proves uploaded file hash and size metadata are correct without requiring huge fixtures.

### 22. Product Images Are Under-Validated And Under-Audited

Problem:

- Image upload uses extension checks only.
- No size limit specific to product images.
- No audit events for image upload/default/POS/delete.

Required fix:

- Add image upload form/validator with size, extension, and content-type checks.
- Use safe image processing or validation if available.
- Audit image upload, default image changes, POS image changes, and deletion.

Tests required:

- Unsafe extension rejected.
- Oversized image rejected.
- Audit events recorded.

## Data Model And Architecture Requirements

Implement the smallest clean model changes needed. Recommended model additions:

- `ProductModelAsset`
  - `id`
  - `product_id`
  - `business_id`
  - `storage_reference`
  - `original_filename`
  - `safe_filename`
  - `content_type`
  - `size_bytes`
  - `sha256`
  - `asset_kind`: source_model, gcode, glb_preview, image, metadata, reference
  - `is_current`
  - `created_at`, `updated_at`

- `ProductAnalysisRun`
  - `id`
  - `product_id`
  - `business_id`
  - `source_asset_id`
  - `requested_by_id`
  - `status`
  - `settings_json`
  - `embedded_settings_json`
  - `geometry_json`
  - `slicer_stats_json`
  - `parsed_volume_mm3`
  - `parsed_surface_area_mm2`
  - `parsed_triangle_count`
  - `parsed_filament_grams`
  - `parsed_print_minutes`
  - `parsed_material_cost`
  - `gcode_asset_id`
  - `preview_asset_id`
  - `metadata_asset_id`
  - `error`
  - `requested_at`
  - `completed_at`
  - `is_current`
  - `superseded_at`

If you choose a different schema, it must still solve race-proofing, evidence, asset clarity, and snapshot traceability.

Migration requirements:

- Add Alembic migration(s).
- Backfill existing product-level model fields into asset/run rows where practical.
- Keep existing `Product` summary fields for compatibility, but document them as denormalized current summary fields.

## Required Tests

Add or update tests to cover:

- Product create validation errors and error rendering.
- Product create launch gate.
- Product edit blocked launch does not persist changes.
- Product edit success still persists and audits.
- Model upload validation, upload size limit, and queue failure handling.
- Model upload creates asset/run records and current state.
- Re-upload/race stale task cannot overwrite current product fields.
- Analysis failure produces failed UI/backend state, not false success.
- Slicer command builder honors or intentionally rejects every visible setting.
- G-code parser covers Prusa, Orca, and Bambu examples.
- Material density defaults and overrides.
- Cost resolver filters by business/material and records fallback warnings.
- Cost snapshot evidence includes analysis/model/hash/settings.
- Only one current cost snapshot remains after repeated calculations.
- Manual cost calculation audit event.
- Automatic analysis cost snapshot audit event.
- Product readiness updates after analysis/costing.
- Image upload validation and audit events.
- **Slicer profiles exist and slicing command builds correctly (mocked).**
- **Concurrent analysis race: start A, start B, complete A after B exists, verify A doesn't overwrite B.**
- **Failed analysis task returns success: false envelope and API reflects error.**
- **Cost snapshot evidence includes model file hash, analysis run ID, slicer settings, material, density.**
- **Filament cost isolation: two businesses, different materials, verify no cross-leakage.**
- **Launch gate blocked edit: verify no product change persisted, no audit event.**
- **Re-analyze resets all parsed/cost fields and clears old assets.**
- **Upload size limit: 413 handler returns friendly JSON/page.**
- **Copies/scale semantics: PMP divides plate cost by copies.**
- **Embedded 3MF settings: detected settings shown, require confirmation, density auto-updates on material change.**
- **Cost confidence: high=exact match, medium=fallback, low=no data, none=no spool cost.**
- **Image upload: size limit, content validation, audit events for upload/default/POS/delete.**
- **Readiness/checklist auto-refresh after AJAX analysis/costing.**
- **Task status envelope standardization across all task types.**
- **PMP uses product's printer profile, not hardcoded.**
- **Market allocation and payment fee rate exposed in UI/API.**
- **analysis_status index added to Product model.**
- **model_analysis_config schema validation and size limits.**
- **Audit outcome field for analysis success/failure distinction.**
- **Launch override reason minimum length validation.**
- **Cost formula version semantic versioning with migration path.**
- **Concurrent cost snapshot creation: only one non-stale snapshot per product.**
- **CSRF enforce on all AJAX mutation endpoints** (upload-model, reanalyze, calculate-costs, upload-image, delete-image, set-default-image, set-pos-image, delete-asset, update-checklist, retire-product, etc.).
- **Rate limiting on all product mutation endpoints** (upload-model, reanalyze, calculate-costs, upload-image, etc.).
- **Business ownership check on product routes** — staff cannot modify products outside their business scope.
- **Model upload magic-byte/content validation** — .stl files must parse as valid STL binary or ASCII; GLB/3MF must match their format.
- **URL validation on model_source_url** — scheme allowlist, no javascript: URIs, phishing detection.
- **Re-analyze idempotency** — cannot queue duplicate analysis when one is already running.
- **Product list sidebar pagination and search** — sidebar must handle large product catalogs.
- **Cost confidence badge visible in cost cards** — UI shows high/medium/low/none confidence.
- **Re-analyze clears cost cards or shows stale state** — user sees cost is stale after re-analysis.
- **Asset deletion is atomic and idempotent** — no dangling DB references on partial failure.
- **Serve product image validates content matches extension** — dangerous files are not served as images.
- **Modal focus trapping and ESC-to-close** — keyboard accessible modals.
- **Asset loading shows skeleton/pulse placeholder** — not just text "Loading assets…".
- **Product sidebar has search and filter** — quick navigation across many products.

## Documentation Updates

Update these docs after implementation:

- `docs/product_creation_developer_flow.md`
- `docs/model_analysis_workflow.md`
- `README.md` if setup commands/config change
- `.env.example` if upload limits, Prusa path, Celery flags, or analysis settings change

Docs must clearly state:

- Which file formats are quoteable.
- Which formats are preview/reference-only.
- How scale and copies are interpreted.
- How material/spool cost is selected.
- What happens when Celery or PrusaSlicer is unavailable.
- How to recover from failed/superseded analysis runs.
- **What the task status envelope looks like for all async operations.**
- **How cost confidence levels are determined.**
- **How copies/scale/PMP affect per-unit cost.**
- **What embedded 3MF settings do and how to confirm them.**
- **How to override filament cost per product when auto-selection is wrong.**
- **Semantic versioning for cost formula and snapshot migration.**

## Verification Commands

Run these before finishing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -v --tb=long
```

If any command cannot run because of environment limitations, document the blocker, but still run all targeted tests that can run.

## Definition Of Done

The work is not done until all conditions are true:

- Blocked launch attempts cannot persist product changes.
- New active/public products cannot bypass launch readiness rules.
- Product validation errors are visible and return correct status codes.
- Model upload queue failures are controlled and recoverable.
- Failed analysis cannot look successful in the UI.
- Re-upload/race conditions cannot corrupt current product analysis/cost fields.
- Uploaded assets have clear current/stale/reference state.
- Every visible slicing setting is either honored or removed/disabled with clear copy.
- Material density and filament cost source are deterministic and auditable.
- Cost snapshots are traceable to exact model/run/settings/hash evidence.
- Manual and automatic cost calculations are audited.
- Upload limits are consistent across config, forms, and UI.
- Relevant product image actions are validated and audited.
- **Slicer profiles exist in repo and slicing works end-to-end (mocked in tests).**
- **Cost confidence levels map to clear evidence: high=exact spool match, medium=fallback, low=no spool cost, none=no model.**
- **PMP uses product's selected printer profile, not hardcoded values.**
- **Copies: plate cost divided by copies for per-unit; item count stored separately.**
- **Scale: all geometry, fit checks, slicing, filament, time reflect selected scale.**
- **Embedded 3MF settings: detected, shown in modal, require confirmation, density auto-updates on material change.**
- **Market allocation and payment fee rate exposed in Product Studio cost inputs.**
- **Readiness/checklist auto-refreshes after AJAX analysis/costing (or page reloads).**
- **Task status envelope standardized: queued/started/validating/slicing/storing_gcode/costing/converting/complete/failed/superseded.**
- **Concurrent analysis: older task superseded, cannot overwrite newer product fields.**
- **Concurrent cost snapshots: only one non-stale snapshot per product.**
- **Cost formula semantic versioning with migration path for old snapshots.**
- **Launch override reason validated for minimum length/content.**
- **Re-analyze: idempotent, resets parsed/cost fields, clears old assets, checks for existing task.**
- **Image upload: size limit, content validation, audit for upload/default/POS/delete.**
- **Cost snapshot inputs include: model file hash, analysis run ID, slicer settings, material, density, scale, copies, parsed values, cost resolver evidence.**
- **Filament cost resolver filters by business_id and material type; cross-business leakage impossible.**
- **Failed analysis tasks: Celery state=SUCCESS but result.success=false; UI shows error, not "complete".**
- **Form validation: 400 on invalid POST, field errors rendered, error summary at top, input preserved.**
- **Upload size: server/form/UI all agree on same limit; 413 handled gracefully.**
- **Uploads streamed to storage, hash computed streaming, no full-file memory copies.**
- **Analysis run table/asset table tracks version, hash, current state; race-proof.**
- **Tests cover all critical paths listed above.**
- **Docs updated to match final behavior.**
- **Ruff and pytest pass, or any environment-only blocker is clearly documented.**
- **CSRF enforced on all AJAX mutation endpoints** — fetch requests with `X-CSRFToken` are validated server-side; missing/invalid tokens return 403.
- **Rate limiting enforced on all product mutation endpoints** — upload, reanalyze, cost calculation, image operations, asset deletion, checklist updates.
- **Business ownership check on all product routes** — no STAFF or ADMIN can modify a product outside their business scope.
- **Model upload validates magic bytes** — file content matches its extension (STL binary/ASCII, GLB, 3MF, OBJ). Text files renamed as .stl are rejected.
- **URL validation on model_source_url** — only http/https schemes allowed; no javascript: URIs.
- **Re-analyze checks for existing running task** — no duplicate Celery tasks; returns clear error if already pending/analyzing.
- **Product sidebar paginated and searchable** — handles large product catalogs without degraded load time.
- **Cost confidence badge visible in cost cards** — UI displays high/medium/low/none with evidence source.
- **Re-analyze clears or marks cost cards stale** — user sees cost estimate is outdated until recalculated.
- **Asset deletion is atomic and idempotent** — no dangling DB references if storage deletion succeeds but DB commit fails; safe retry.
- **Serve product image validates content matches extension** — dangerous files are not served with misleading content-type.
- **Modal focus trapping and ESC-to-close** — keyboard accessible; focus stays within modal while open.
- **Asset grid shows skeleton/pulse placeholder** — loading state is visually clear with animated placeholders.
- **Product sidebar has search and filter** — quick navigation by name, SKU, or slug across all products.

## Additional Critical Issues Found In Second Pass

### 23. Slicer Profiles Directory Missing At Runtime
Problem:
- `app/services/model_analysis.py:59-64` expects `.ini` profiles in `SLICER_PROFILES_DIR` (`app/services/slicer_profiles/`).
- This directory does not exist in the repository.
- First slicing attempt will fail with "profile not found" falling back to default which also doesn't exist.

Required fix:
- Add `bambu_a1.ini`, `bambu_x1c.ini`, `bambu_p1p.ini` PrusaSlicer profile files to `app/services/slicer_profiles/`.
- Or change default to a known-good built-in profile and document that custom profiles go in that directory.
- Ensure the directory is created at startup if missing.

### 24. Embedded 3MF Settings Can Silently Override User Selections
Problem:
- `model_analysis.py:253-273`: when `use_embedded_settings` is true (default), embedded 3MF settings overwrite `analysis_config` keys including `material`, `infill_percent`, `infill_pattern`, `supports`.
- This happens without user confirmation or visibility in the UI after upload.
- Material change from embedded settings does NOT update `filament_density`, causing density mismatch.

Required fix:
- Make embedded settings application explicit: show detected embedded settings in UI, require confirmation before applying.
- When material changes via embedded settings, auto-update density to material default unless user has manually overridden.
- Log/audit which settings came from embedded vs user-selected.

### 25. Cost Confidence Logic Is Flawed
Problem:
- `cost_engine.py:243-245`: `confidence = "high" if selected_spool_id is not None and resolved_failure_rate > Decimal("0") else "medium"`
- This means "high" confidence REQUIRES a non-zero failure rate, which is backwards.
- If no spool match, confidence becomes "low" but the cost is still calculated with `cost_per_gram = 0`.

Required fix:
- Confidence should be: "high" when exact material/spool match with cost data, "medium" when fallback average used, "low" when no spool data at all.
- Failure rate should not gate confidence.
- When `cost_per_gram == 0`, force confidence to "none" and evidence_source to "no_spool_cost".

### 26. Cost Snapshot Concurrency - No Transaction Isolation
Problem:
- `cost_engine.py:313-316`: marks old snapshots stale, then creates new one. Two concurrent calculations can both see the same "current" snapshot, both mark it stale, both create new ones.
- No database-level constraint ensures only one non-stale snapshot per product.

Required fix:
- Use `SELECT FOR UPDATE` or advisory lock when creating snapshots.
- Add unique partial index: `CREATE UNIQUE INDEX uq_cost_snapshot_current ON cost_snapshots (product_id) WHERE stale = false;` (PostgreSQL) or handle in transaction logic for MariaDB.
- Make stale/current transition atomic.

### 27. Re-Analyze Doesn't Reset Cost Fields
Problem:
- `studio_routes.py:728-731`: `reanalyze_model` resets `analysis_status`, `analysis_error`, `analysis_completed_at`, `analysis_requested_at` but does NOT reset `parsed_filament_grams`, `parsed_print_minutes`, `parsed_material_cost`, `estimated_material_cost`, `estimated_profit`, `estimated_print_minutes`.
- User clicks Re-analyze, old cost numbers remain visible until new analysis completes, creating confusion.

Required fix:
- `reanalyze_model` must also clear: `parsed_filament_grams`, `parsed_print_minutes`, `parsed_material_cost`, `parsed_volume_mm3`, `parsed_surface_area_mm2`, `parsed_triangle_count`, `estimated_material_cost`, `estimated_profit`, `estimated_print_minutes`, `gcode_path`, `converted_model_path`, `convert_status`, `conversion_error`, `model_metadata_path`.
- Or better: delegate to a service function that does a full analysis reset.

### 28. No Request-Too-Large Handling For Oversized Uploads
Problem:
- Flask's `MAX_CONTENT_LENGTH` (default 16MB) triggers a 413 Request Entity Too Large before the form validation runs.
- User sees a generic browser error page, not a friendly JSON/form error.

Required fix:
- Add a global error handler for 413 that returns JSON for AJAX uploads and a friendly page for form posts.
- Or increase `MAX_CONTENT_LENGTH_MB` to match the form limit (256MB) and document it.
- Ensure `.env.example` includes the correct value.

### 29. PrusaSlicer `nozzle_diameter` And `filament_density` Not Passed To CLI
Problem:
- `model_analysis.py:240-257`: `cli_values` dict only includes layer_height, perimeters, top/bottom layers, infill_pattern, brim_width.
- `nozzle_diameter` and `filament_density` are stored in config but never passed to PrusaSlicer.
- `filament_density` IS used in G-code parsing fallback (line 284) but not in slicing.

Required fix:
- Add `--nozzle-diameter` and any density-related flags to PrusaSlicer CLI if supported.
- If not supported by PrusaSlicer CLI, remove these fields from the UI or mark as "metadata only, does not affect slicing".

### 30. Copies And Scale Semantics Are Undefined For Costing
Problem:
- `copies` and `scale_percent` are accepted in upload form and stored in `model_analysis_config`.
- `slice_with_prusaslicer` does not use `copies` (PrusaSlicer CLI has no `--copies` for FFF).
- `scale_percent` is not passed to slicer.
- Cost engine uses parsed grams/time from single-item slice, but if user intended multiple copies per plate, the per-unit cost is wrong.

Required fix:
- Define semantics: "copies" = number of parts arranged on one build plate by PMP (post-process), OR "copies" = printed sequentially (not supported by PrusaSlicer CLI for FFF).
- If PMP: slicing is for 1 copy, PMP arranges N copies, cost per unit = plate_cost / N.
- If sequential: not supported, remove field or disable.
- `scale_percent`: apply to model geometry before slicing (trimesh scale) OR pass to PrusaSlicer `--scale` if supported.
- Update cost engine to divide plate cost by copies when PMP is used.

### 31. `preserve_orientation` And `multicolor` Are UI-Only
Problem:
- Both fields stored in `model_analysis_config` but never used anywhere in slicing, validation, or costing.
- `multicolor` implies wipe tower/prime tower but no PrusaSlicer flags are set.

Required fix:
- Implement or remove. For `multicolor`: add `--support-material` + wipe tower settings if PrusaSlicer supports it. For `preserve_orientation`: skip the `--center` flag in slicer command.

### 32. Missing `trimesh` / PrusaSlicer Runtime Checks In Production Path
Problem:
- `model_analysis.py:126-129` and `222-224` return error results but the Celery task treats them as task failures (retries).
- No startup health check validates that `trimesh` and `PrusaSlicer` are available.
- Production deployments can silently fail analysis tasks.

Required fix:
- Add a startup health check (e.g., in `create_app` or a CLI command) that verifies `trimesh` import and `PrusaSlicer --help-fff`.
- On missing dependency, set a clear app config flag and show admin warning in Product Studio.
- In task, fail fast with a non-retryable error if dependencies missing, so UI shows actionable message.

### 33. Product Create Doesn't Validate Category Exists Before Form Render
Problem:
- `ProductStudioForm.__init__` loads categories from DB (line 78-80).
- If no categories exist, `category_id` choices is empty but field is `DataRequired()`.
- User sees empty dropdown and cannot submit.

Required fix:
- In `studio` route GET, if no categories exist, flash a warning and redirect to category management, or auto-create a default category.
- Render a helpful message in the template when category choices are empty.

### 34. Image Upload Uses `file.read()` Without Size Limit
Problem:
- `studio_routes.py:835`: `file.read()` loads entire image into memory.
- No Flask-level size limit for product images (only global 16MB).
- No validation of actual image content (could be non-image with .jpg extension).

Required fix:
- Add `FileSize` validator to image upload (separate from model upload).
- Stream image to storage or validate via PIL/Pillow before committing.
- Audit image upload, default/POS assignment, and deletion.

### 35. Readiness/Checklist Not Refreshed After AJAX Analysis/Costing
Problem:
- `studio.js:157-168` only refreshes three metric cards after analysis.
- Readiness score, launch checklist, and photo shots don't update until full page reload.
- User sees "Model analyzed" checklist item still unchecked after analysis completes.

Required fix:
- After successful analysis/costing, either reload page or fetch and re-render readiness/checklist partials.
- Simpler: add `location.reload()` after analysis and conversion both complete (already done for re-analyze at line 444).

### 36. Task Status Envelope Inconsistent Between Routes
Problem:
- `/task-status` returns `{state, result, error, traceback, info}` (studio_routes.py:663-681).
- Analysis task returns `{"success": True/False, ...}` inside `result`.
- Cost task returns breakdown dict inside `result`.
- No standard envelope makes frontend handling fragile.

Required fix:
- Standardize: all tasks return `{"success": bool, "data": {...}, "error": "..."}`.
- `task-status` endpoint wraps Celery result into this envelope.
- Frontend checks `data.success` not just `state === SUCCESS`.

### 37. PMP Task Uses Hardcoded Printer "u1"
Problem:
- `model_analysis.py:80`: `printer="u1"` hardcoded in `pack_model_bytes` call.
- Should use the product's selected printer profile or a configurable default.

Required fix:
- Pass printer profile from product/asset settings to PMP task.
- Store printer used in PMP metadata.

### 38. Cost Engine `market_allocation` And `payment_fee_rate` Never Exposed In UI
Problem:
- `calculate_product_cost` accepts `market_allocation` and `payment_fee_rate` but Product Studio never collects or passes them.
- Market costs and card fees are excluded from product-level costing.

Required fix:
- Add optional market allocation field to cost inputs (per-product or per-market).
- Add payment fee rate field or use global setting with override.
- Pass them in manual cost calculation and API.

### 39. No Database Index On `Product.analysis_status`
Problem:
- Frequent queries filter by `analysis_status` (e.g., pending, complete, failed).
- No index on this column in `catalog.py:144`.

Required fix:
- Add `index=True` to `analysis_status` column.

### 40. `model_analysis_config` JSON Column Can Grow Unbounded
Problem:
- `catalog.py:163`: `model_analysis_config` is a JSON column storing all slicer settings, embedded settings, geometry, slicer results.
- Over multiple re-analyses, `embedded_settings_detected`, `slicer_results`, `geometry` accumulate.
- No size limit or cleanup.

Required fix:
- Define a fixed schema for allowed keys.
- On each write, strip unknown keys.
- Consider moving large results (slicer_results, geometry) to separate columns or asset metadata files.

### 41. No Audit For `model_analysis.completed` vs `model_analysis.failed` Distinction
Problem:
- Both completion and failure record `model_analysis.completed` / `model_analysis.failed` but the audit metadata doesn't clearly distinguish success vs failure in a queryable way.
- `model_analysis.failed` is recorded but with `actor_type="system"`.

Required fix:
- Ensure audit events have consistent `action` names and include `success: true/false` in metadata.
- Add `outcome` field to audit schema if not present.

### 42. `ProductLaunchChecklistItem` `override_reason` Not Validated
Problem:
- Any text can be entered as override reason, including empty/whitespace.
- `launch_gate` (product_ops.py:239) treats non-empty string as override regardless of content.

Required fix:
- Require minimum length (e.g., 10 chars) for override reason.
- Validate on form submit and in `launch_gate`.

### 43. Cost Formula Version Not Semantic Or Dated Properly
Problem:
- `cost_engine.py:28`: `COST_FORMULA_VERSION = "2026-06-26.product-studio-v1"`
- Not semantic versioning, no way to detect breaking changes vs patches.
- Snapshots store this but no migration path for old snapshots.

Required fix:
- Use semantic version: `MAJOR.MINOR.PATCH` (e.g., `1.0.0`).
- Increment MAJOR for breaking formula changes, MINOR for new inputs, PATCH for fixes.
- Store version in snapshot and provide re-calculation migration for old versions.

### 44. No Test For Concurrent Analysis Race Condition
Problem:
- The race condition in issue 6 is not covered by any test.
- Critical for data integrity.

Required fix:
- Add test: start analysis A, start analysis B, complete A after B exists, verify A's results don't overwrite B's.

### 45. No Test For Failed Analysis UI State
Problem:
- The false-success UI bug (issue 5) has no test coverage.

Required fix:
- Add test that mocks a failed analysis task and verifies the API returns `success: false` and the frontend would show error state.

### 46. No Test For Cost Snapshot Evidence Traceability
Problem:
- Cost snapshot evidence requirements (issue 15) have no test.

Required fix:
- Add test verifying snapshot inputs include model file hash, analysis run ID, slicer settings, material, density.

### 47. No Test For Filament Cost Business/Material Isolation
Problem:
- The cross-business/material cost leakage (issue 13) has no test.

Required fix:
- Add test with two businesses, different materials, verify costs don't leak.

### 48. No Test For Launch Gate Blocking Persistence
Problem:
- The blocked-edit persistence bug (issue 1) has no test.

Required fix:
- Add test verifying blocked edit doesn't persist product changes or audit event.

### 49. Missing Slicer Profiles - Startup Failure
Problem:
- Without `bambu_a1.ini` etc., first analysis fails.
- No test verifies profiles exist or slicing works end-to-end.

Required fix:
- Add minimal PrusaSlicer profile files to repo.
- Add integration test (mocked) that verifies slicing command is built correctly.

### 50. Re-Analyze Should Be Idempotent And Safe
Problem:
- `reanalyze_model` can be called while analysis is already running.
- No check for existing pending/analyzing task.

Required fix:
- Check `analysis_status` before queuing; if `pending` or `analyzing`, return current task_id or error.
- Or allow re-queue but cancel/supersede previous task (requires task revocation support).

## Final Security & Completeness Pass — Additional Findings

### 51. AJAX Endpoints Lack CSRF Enforcement For Fetch Requests
Problem:
- The JS `studio.js` sends `X-CSRFToken` header on every POST/DELETE fetch (upload-model, reanalyze, calculate-costs, upload-image, set-default-image, set-pos-image, delete-image, delete-asset, update-checklist, update-photo, retire-product, etc.).
- Flask-WTF CSRF protection is form-based by default. There is no explicit middleware or decorator that validates `X-CSRFToken` for AJAX/fetch requests on these product-routes endpoints.
- An attacker can craft a malicious page that POSTs to `/products/studio/<id>/upload-model` with a valid session cookie and bypass CSRF.

Required fix:
- Enable `WTF_CSRF_CHECK_DEFAULT = True` in Flask config, or add a custom `@csrf_protect_api` decorator that reads `X-CSRFToken` header and validates it against the session token.
- Apply it to all mutation endpoints used by JavaScript fetch calls.
- Ensure the 413 error handler also returns a valid CSRF error context so no fallback bypass exists.

Tests required:
- Unit test: POST to upload-model with missing/invalid `X-CSRFToken` returns 403.
- Unit test: POST to reanalyze with valid session but missing header returns 403.
- Unit test: DELETE to delete-image with invalid token returns 403.

### 52. No Rate Limiting On Product Mutation Endpoints
Problem:
- Endpoints for upload-model, reanalyze, calculate-costs, upload-image, set-default-image, set-pos-image, retire-product, and asset deletion have no rate limiting.
- A misbehaving user or integration can hammer these endpoints and degrade the Celery queue or storage backend.
- Unlike the API token route (which uses `rate_limit` in `auth.py`), none of the product studio routes enforce request throttling.

Required fix:
- Add Flask-Limiter or equivalent rate limiting to all product mutation endpoints.
- Reasonable defaults: 60 requests/minute for upload, 30/minute for calculate-costs, 30/minute for reanalyze, 120/minute for image operations.
- Return `429 Retry-After` with a useful message when throttled.

Tests required:
- Send 20 rapid upload-model requests and assert 429 after the limit.
- Verify rate limit resets after the window expires.

### 53. No Business/Ownership Check On Product Routes
Problem:
- Any user with `ADMIN` or `STAFF` role can modify any product, regardless of `business_id`.
- The `get_by_id(Product, product_id)` call does not filter by `current_user.business_id`.
- In a future multi-business setup, a staff user in Business A could modify Business B's product models, costs, and images.
- Even in single-business mode, this sets a dangerous precedent and leaks data if the user table ever has a `business_id` column.

Required fix:
- Add a `business_id` check to `studio_routes` and all product CRUD operations.
- Either enforce `Product.business_id == current_user.business_id` (for multi-business) or at minimum log a warning when roles mismatch and the user is STAFF (not ADMIN).
- Apply `@roles_required(UserRole.ADMIN)` for destructive operations (retire, delete asset, delete image); STAFF should only edit non-destructive fields.

Tests required:
- STAFF user cannot retire a product (or gets a 403).
- Product from a different business cannot be reached (when multi-business is enabled).

### 54. `model_source_url` Has No URL Validation
Problem:
- `ProductStudioForm.model_source_url` accepts any text up to 500 characters.
- No URL format validation, no scheme allowlist, no hostname allowlist.
- Could be used to store phishing URLs, internal network addresses (SSRF if the URL is ever fetched), or JavaScript URIs (`javascript:`).

Required fix:
- Add `URL` validator to the form field.
- Allow only `http://` and `https://` schemes.
- Optionally add an allowlist of trusted domains (e.g., thingiverse.com, printables.com, myminifactory.com).
- Store a normalized/validated URL, not raw user input.

Tests required:
- `javascript:` URI is rejected.
- `ftp://` URI is rejected.
- Valid HTTPS URL is accepted and normalized.

### 55. `launch_override_reason` Textarea Has No Max Length
Problem:
- `ProductStudioForm.launch_override_reason` is a `TextAreaField` with `Length(max=...)` not set beyond the default WTForms `TextAreaField` limit (effectively unlimited).
- Could store arbitrarily large text, creating data pollution and potential stored-XSS surface if ever rendered unsafely in an admin console or API response.

Required fix:
- Add `Length(max=2000)` validator.
- Strip and truncate on form populate.
- Consider a `CharField` with a reasonable max length if multiline is not strictly needed.

Tests required:
- 3000-character override reason is rejected.
- 2000-character override reason is accepted.

### 56. No Magic-Byte / Content-Type Validation On Model Uploads
Problem:
- Model upload validates extension (`.stl`, `.glb`, `.gltf`, `.3mf`, `.obj`) and size (256 MB).
- It does NOT validate the file's actual content type or magic bytes.
- A malicious file with `.stl` extension containing embedded scripts or excessive payloads passes validation.
- This is a supply-chain and denial-of-service risk.

Required fix:
- After size check, read the first bytes and verify the file matches the expected format magic number.
- STL (binary): first 80 bytes are header, then 4-byte triangle count.
- STL (ASCII): starts with `solid`.
- GLB: starts with GLB magic bytes `glTF`.
- 3MF: ZIP file with `[Content_Types].xml`.
- OBJ: starts with `#` or `o ` or `v `.
- On mismatch, reject with clear error.

Tests required:
- Uploading a `.stl` file with GLB magic bytes is rejected.
- Uploading a text file renamed to `.stl` is rejected.

### 57. `trend_score` Endpoint Has Fragile Deep Import And Info-Leak Risk
Problem:
- `studio_routes.py:975` imports from `app.services.ai.trend_scout.analyzer.trend_detector`.
- These modules may not exist in a fresh install or after a refactor.
- When the import fails, the error is caught by a broad `except Exception` and returns the full error message in JSON: `f"Catalog/metrics calculation failed: {e}"`.
- This can leak internal implementation details, module paths, and dependency names to attackers.

Required fix:
- Move the import to the top of the file or use lazy import with a specific `ImportError` catch.
- Return a generic error message in production (e.g., "Trend scoring is temporarily unavailable").
- Log the detailed error server-side only.
- Add a feature flag to disable the trend score feature entirely if the AI dependency chain is not present.

Tests required:
- Test that a missing import does not crash the route and returns a generic message.
- Test that the route 404s or 503s when the trend scout module is not available.

### 58. `reanalyze_model` Does Not Check For Existing Running Task
Problem:
- Issue 50 noted this but the fix is not yet in code.
- `reanalyze_model` resets `analysis_status = "pending"` and queues a new task immediately.
- If a previous analysis task is still running (status `analyzing`), both tasks operate on the same product.
- The older task can overwrite results after the newer one completes.

Required fix:
- At the start of `reanalyze_model`, check if `product.analysis_status` is `pending` or `analyzing`.
- If so, return a JSON response explaining that a task is already running and provide the current task ID if available, or require the user to wait/cancel.
- Optionally add a `revoke` mechanism to cancel the previous task before re-queuing.

Tests required:
- Calling re-analyze while a task is pending returns a clear error JSON, not a new task_id.
- Calling re-analyze after completion queues a fresh task.

### 59. Product List Sidebar Has No Pagination Or Search
Problem:
- `_load_products()` in `studio_routes.py` loads ALL products into memory: `Product.query.filter(...).order_by(...).all()`.
- The sidebar renders every product as a clickable link with no pagination, no virtual scrolling, and no search/filter.
- With hundreds of products, this degrades page load time and sidebar usability.

Required fix:
- Add pagination to the product list query (e.g., `paginate(page=1, per_page=50)`).
- Add a search/filter input to the sidebar.
- Or at minimum, add `query_factory` in the template and paginate, with a "Load more" or numbered pager.

Tests required:
- Product list sidebar renders paginated results when product count exceeds page size.
- Search input filters products by name/slug/SKU client-side or server-side.

### 60. `serve_product_image` Endpoint Doesn't Validate Content-Type For Serving
Problem:
- `serve_product_image` uses `content_type_for_name(download_name)` which relies on the filename extension.
- If a non-image file was uploaded with an `.jpg` extension (bypassing upload validation), `send_file` will serve it with `image/jpeg` content-type.
- Browsers may attempt to render it as an image, causing errors or unexpected behavior.
- If the uploaded file contained executable content disguised as an image, this serves it with a dangerous content-type.

Required fix:
- After retrieving the file from storage or disk, inspect the magic bytes to verify it matches the expected image format based on the extension.
- If mismatch, serve with `application/octet-stream` or abort with 400.
- Alternatively, validate magic bytes at upload time (see issue 56) and trust the stored metadata for serving.

### 61. Asset Deletion Leaves Product In Inconsistent State On Partial Failure
Problem:
- `delete_product_asset` deletes the storage file first, then adjusts `Product` model fields, then commits.
- If the storage deletion succeeds but the `db.session.commit()` fails (e.g., database constraint error, connection lost), the storage file is gone but the `Product` still references it.
- This leaves a dangling reference that cannot be recovered without manual cleanup.

Required fix:
- Use a database transaction that groups the Product field changes and metadata updates before deleting physical files.
- Delete physical files only after the database commit succeeds.
- Or use a two-phase approach: mark the asset as deleted in the database first, then delete storage asynchronously.

Tests required:
- Simulate DB commit failure after storage deletion and verify no dangling reference remains.
- Verify deletion is idempotent (deleting an already-deleted asset returns success, not error).

### 62. Missing UI: Cost Confidence Level Not Displayed In Cost Cards
Problem:
- The `cost_result` endpoint returns `confidence` and `evidence_source` in the JSON.
- The `showCostResult` function in `studio.js` does not display confidence level or evidence source in the cost cards UI.
- Users cannot tell if the cost estimate is high-confidence (exact spool match), medium (fallback), low (no spool), or none (no model).

Required fix:
- Add a confidence indicator to the cost results cards (e.g., a small badge or icon showing "High confidence", "Fallback", "Low confidence", "No model data").
- Show evidence source on hover or in an expandable details section.

Tests required:
- UI test (manual or integration) verifies confidence badge renders correctly for each level.

### 63. Missing UI: No Indication That Re-Analyze Resets Cost Fields
Problem:
- When `reanalyze_model` is called, the route resets analysis fields but the cost cards on the page (`estimated_material_cost`, `estimated_profit`, `estimated_print_minutes`) are NOT cleared or updated.
- After re-analysis the user sees old cost numbers until they manually click "Calculate Cost" or reload.
- The JS `refreshAnalysisResult` only updates three metric cards and does not update cost cards or readiness.

Required fix:
- After re-analysis completes (or is queued), clear the cost cards or show a "calculating..." state.
- After analysis completes, auto-refresh cost results or show a "Cost may be stale — recalculate" banner.
- Alternatively, add `location.reload()` after successful re-analysis (already done for the re-analyze button at line 444 of studio.js, but the cost cards should be cleared before reload).

Tests required:
- After re-analysis is dispatched, the cost cards show a stale/loading state.
- After re-analysis completes, the cost cards update to reflect new data.

### 64. Upload Size Limit Config Is Inconsistent With Error Handling
Problem:
- `MAX_CONTENT_LENGTH` default is 16 MB (in `config.py`).
- The upload form and UI claim 256 MB is allowed.
- The `ProductModelUploadForm` has `FileSize(max_size=256 * 1024 * 1024)`.
- If a 20 MB file is uploaded, Flask rejects the request with a 413 BEFORE the form validates it, with no friendly error page.
- If a 300 MB file is uploaded, the same 413 happens.

Required fix:
- Align `MAX_CONTENT_LENGTH_MB` to the form/UI claim (256 MB) or reduce the form/UI to 16 MB.
- Add a global 413 error handler that returns JSON for AJAX uploads and a friendly HTML page for form posts.
- Document the actual limit in `.env.example`.

This is partially covered by issue 28 but needs the explicit config-alignment fix and error handler.

### 65. No `updated_at` Touch On Config-Only Updates
Problem:
- When `model_analysis_config` is updated (e.g., during analysis or re-analysis), `updated_at` on the `Product` row is not explicitly touched by the code.
- SQLAlchemy does not automatically update `updated_at` unless the model is marked as dirty. However, some updates (like `analysis_status` changes) may not flag enough columns to trigger a `before_update` event update of `updated_at`.
- This can cause issues if downstream consumers rely on `updated_at` to determine when the product was last modified.

Required fix:
- Ensure `updated_at` is explicitly set to `datetime.now(timezone.utc)` whenever `analysis_status`, `model_analysis_config`, or other key fields are modified.
- Or add a SQLAlchemy event listener that touches `updated_at` on any change.

### 66. No Download/View Safety Check For Model Files
Problem:
- `download_model` and `view_model` endpoints use `send_file` directly on the resolved file path.
- If the file does not exist (e.g., after deletion but before DB cleanup), `send_file` will raise a 404 or 500 with a stack trace depending on Flask config.
- If the file exists but is not a valid 3D model (e.g., corrupted), `send_file` serves it as-is without content-disposition or content-type safety enforcement.

Required fix:
- Verify the file exists before attempting `send_file`.
- Explicitly set `mimetype` and `as_attachment` for download endpoint.
- For `view_model`, set `mimetype="model/gltf-binary"` for `.glb` files and let the viewer handle it.
- Return a friendly 404 or 422 if the file cannot be found or is invalid.

### 67. No Keyboard Accessibility For Modal Close Buttons
Problem:
- Modal close buttons use `×` text or `data-close-*` attributes but are plain `<button>` elements without explicit `type="button"` in all cases and without `tabindex` management.
- The upload-settings-modal and assets-modal do not trap keyboard focus — pressing Tab from inside the modal can focus elements behind the modal.
- ESC key does not close any of the modals.

Required fix:
- Add `type="button"` to all modal close buttons.
- Implement focus trapping inside modals (contain Tab/Shift+Tab cycling within the modal).
- Add ESC key handler to close modals.
- Add `aria-hidden` to the rest of the page when a modal is open.

### 68. No Skeleton/Loading State For Asset Grid Or Cost Cards
Problem:
- The asset modal shows "Loading assets…" text but no skeleton/pulse animation.
- Cost calculation shows a "Calculating costs..." pulse animation but cost cards are replaced by it without preserving the card layout.
- No empty-state illustration for zero assets.
- No "Retry" button for failed asset loads.

Required fix:
- Add skeleton cards or pulse placeholders while assets load.
- Add retry button for failed asset loads.
- Add empty-state illustration/message when no assets exist (already partially done).
- Ensure cost card loading state preserves the 4-column grid layout.

### 69. No Product Search Filter On The Studio Page
Problem:
- The product list sidebar in the studio shows all products sorted by updated_at desc.
- There is no search box, category filter, or status filter.
- For shops with many products, finding a specific product requires scrolling through the entire list.

Required fix:
- Add a search input that filters the sidebar product list by name, SKU, or slug.
- Optionally add category and status filter pills.

### 70. Image Upload Endpoint Does Not Validate Actual Image Content
Problem:
- `upload_product_image` at line 821-829 checks file extension only (`ext not in (.jpg, .jpeg, .png, .webp, .gif)`).
- It then calls `file.read()` and uploads to storage.
- A malicious script (e.g., a PHP file) renamed to `.jpg` will be accepted, stored, and served by `serve_product_image` with a potentially dangerous content-type or cause browser confusion.
- No magic-byte validation is performed.

Required fix:
- After extension check, validate the file's magic bytes against the expected format.
- Use PIL/Pillow (or `imghdr`/`filetype` library) to verify the file is a valid image.
- Reject files that don't match their extension's expected binary format.

Tests required:
- Upload a text file renamed to `.jpg` — rejected.
- Upload a PHP script renamed to `.jpg` — rejected.
- Upload a valid JPEG — accepted.

## Final Pass Consolidated Summary

### By Category

#### Security (6 new)
| # | Issue | Severity |
|---|-------|----------|
| 51 | AJAX endpoints lack CSRF enforcement for fetch requests | Critical |
| 52 | No rate limiting on product mutation endpoints | High |
| 53 | No business/ownership check on product routes | High |
| 54 | `model_source_url` has no URL validation (phishing/SSRF) | Medium |
| 56 | No magic-byte/content validation on model uploads | High |
| 57 | `trend_score` fragile deep import with info-leak error messages | Medium |
| 70 | Image upload does not validate actual image content | High |

#### Data Integrity & Completeness (6 new)
| # | Issue | Severity |
|---|-------|----------|
| 58 | `reanalyze_model` doesn't check for existing running task | High |
| 59 | Product list sidebar has no pagination or search | Medium |
| 61 | Asset deletion leaves product in inconsistent state on partial failure | High |
| 63 | No indication that re-analyze resets cost fields | Medium |
| 65 | No `updated_at` touch on config-only updates | Low |
| 69 | No product search filter on the studio page | Medium |

#### UI/UX Changes (5 new)
| # | Issue | Severity |
|---|-------|----------|
| 62 | Cost confidence level not displayed in cost cards | Medium |
| 67 | No keyboard accessibility for modal close buttons (no focus trap, no ESC) | Medium |
| 68 | No skeleton/pulse loading state for asset grid or cost cards | Low |
| 71 | 413 error handler needs alignment with actual configured limit (issue 28 continuation) | Medium |
| 64 | Upload size limit config inconsistent with error handling (issue 28 detail) | Medium |

#### API/Backend Gaps (4 new)
| # | Issue | Severity |
|---|-------|----------|
| 55 | `launch_override_reason` textarea has no max length | Low |
| 60 | `serve_product_image` doesn't validate content matches extension | Medium |
| 66 | `download_model`/`view_model` serve files without safety checks | Medium |
| 50 (revisited) | Re-analyze should be idempotent — fix not yet in code | High |

### Totals

- Original first pass: 22 issues (issues 1-22)
- Second pass additions: 28 issues (issues 23-50)
- Final pass additions: 20 issues (issues 51-70)
- **Grand total: 70 issues**
- Critical: 1 (CSRF on AJAX endpoints)
- High: 11 (rate limiting, ownership check, magic-byte validation, re-analyze race, asset deletion atomicity, etc.)
- Medium: 10 (confidence display, keyboard accessibility, URL validation, content-type serving, etc.)
- Low: 3 (override reason max length, `updated_at` touch, loading skeleton)
