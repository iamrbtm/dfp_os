# Product Flow Gap Remediation — Milestones & Phases

**Total issues tracked: 55 (all preserved from the source prompt, zero omitted)**

---

## Phase 0: Data Model & Schema Foundation

**Goal:** Build the database tables and schema changes needed to support race-proof analysis, traceable cost snapshots, clean asset management, and indexed queries. Everything else depends on these.

**Estimated effort:** High — involves new SQLAlchemy models, Alembic migrations, backfill logic, and existing-product compatibility.

### Issue 6 — Background Analysis Is Race-Prone Across Re-uploads

**What's wrong:** Product analysis state lives directly on the `Product` row. If you upload model A then immediately upload model B before A finishes, A's background task overwrites B's fields. Cost snapshots don't store what file they came from.

**What to do (step by step like you're telling a 5-year-old):**
1. Create a new database table called `ProductModelAsset`. Each row in this table represents one file that was uploaded or generated for a product — the original STL, the G-code that came from slicing it, the GLB preview, etc.
2. Add columns to `ProductModelAsset`: `id` (unique number for each row), `product_id` (which product this belongs to), `business_id` (which business owns it), `storage_reference` (where the file lives on disk or S3), `original_filename` (the name the user uploaded), `safe_filename` (the cleaned name we store), `content_type` (like `model/stl` or `text/gcode`), `size_bytes` (how big the file is), `sha256` (a fingerprint that proves the file hasn't changed), `asset_kind` (what kind: `source_model`, `gcode`, `glb_preview`, `image`, `metadata`, `reference`), `is_current` (is this the active/current version?), `created_at`, `updated_at`.
3. Create another new table called `ProductAnalysisRun`. Each row records one attempt at analyzing a product's model.
4. Add columns to `ProductAnalysisRun`: `id`, `product_id`, `business_id`, `source_asset_id` (which asset was analyzed), `requested_by_id` (who asked for the analysis), `status` (what stage: queued, started, validating, slicing, storing_gcode, costing, converting, complete, failed, superseded), `settings_json` (the slicer settings used), `embedded_settings_json` (settings embedded in the 3MF file), `geometry_json`, `slicer_stats_json`, `parsed_volume_mm3`, `parsed_surface_area_mm2`, `parsed_triangle_count`, `parsed_filament_grams`, `parsed_print_minutes`, `parsed_material_cost`, `gcode_asset_id`, `preview_asset_id`, `metadata_asset_id`, `error` (what went wrong, if anything), `requested_at`, `completed_at`, `is_current`, `superseded_at`.
5. Keep the existing summary fields on `Product` (like `parsed_filament_grams`, `analysis_status`) so the rest of the code still works, but add a comment above each one saying "This is a summary copied from the latest current ProductAnalysisRun — don't write to it directly in most cases."
6. Create an Alembic migration that adds these tables and backfills existing product model info into the new tables.
7. Update the Celery tasks so they receive the `analysis_run_id` and `source_asset_id`. Before writing results, the task checks: "Am I still the current run for this product?" If not, the task marks itself as `superseded` and does NOT write to the product fields.
8. Write a test that starts analysis run A, starts analysis run B (same product), completes A AFTER B exists, and verifies A's results never touched B's product fields.

### Issue 7 — Re-upload Leaves Old Assets And Ambiguous State

**What's wrong:** When you upload a new model, the old `product.model_file_path` is replaced but the old files are still on the server. The asset list shows everything with no way to tell which is the current model.

**What to do (step by step):**
1. In the `ProductModelAsset` table (from Issue 6), every source model file has `is_current = True` or `is_current = False`.
2. When a new model is uploaded, mark all old `source_model` assets for this product as `is_current = False`.
3. In the Assets modal in Product Studio, add labels: "Current source model", "Current G-code", "Current GLB preview", "Stale asset (v2)", "Metadata file".
4. Decide on a retention rule: "Keep stale assets for history" or "Archive after 30 days" or "Delete on user confirmation." Implement it.
5. When someone deletes a current asset, either block it with a warning ("This is the current model — are you sure?") or safely reset the product's analysis fields.
6. Write tests: upload + re-upload creates clear current/stale labels; deleting a stale asset doesn't damage current analysis.

### Issue 15 — Cost Snapshots Are Not Strong Enough As Evidence

**What's wrong:** Cost snapshots don't record what model file, what hash, what analysis run, what slicer settings, or what density were used. A snapshot can be recalculated later and give different numbers, but the old snapshot still claims to be "the cost at analysis time."

**What to do (step by step):**
1. Add columns to the `CostSnapshot` table: `model_asset_id`, `analysis_run_id`, `file_sha256`, `slicer_settings_hash`, `material`, `density`, `density_source` (did it come from a default, an embedded 3MF file, or a manual override?), `scale_percent`, `copies`, `parsed_filament_grams`, `parsed_print_minutes`, `cost_resolver_evidence_json` (a JSON blob that records which spools were matched, what the weighted average was, any fallback reason).
2. When creating a cost snapshot, always fill in these columns. Never create a snapshot without linking it to a model asset and analysis run.
3. Enforce "one current snapshot per product at a time" — when a new snapshot is saved, the old one becomes `stale = True`.

### Issue 26 — Cost Snapshot Concurrency — No Transaction Isolation

**What's wrong:** Two people clicking "Calculate Cost" at the same time can both read the same "current" snapshot, both mark it stale, and both create a new snapshot. Now you have two "current" snapshots.

**What to do (step by step):**
1. When creating a cost snapshot, use `SELECT ... FOR UPDATE` (a database lock) on the product row so that only one thread can be making a new snapshot at a time.
2. In the same transaction: mark old snapshots stale, insert the new snapshot, commit.
3. Add a partial unique index on `cost_snapshots`: `WHERE stale = false AND product_id = ?` if the database supports it. For MariaDB, handle it with application-level locking via `with db.session.begin_nested()`.
4. Write a test: start two concurrent cost calculations, verify only one "current" snapshot exists afterward.

### Issue 39 — No Database Index On `Product.analysis_status`

**What's wrong:** The code frequently runs queries like "find all products where analysis_status = 'pending'" and this scans every row because there's no index.

**What to do (step by step):**
1. Open `app/models/catalog.py`, find the `analysis_status` column.
2. Add `index=True` to it.
3. Create a migration that adds the index to the database.

### Issue 40 — `model_analysis_config` JSON Column Can Grow Unbounded

**What's wrong:** Every time a re-analysis happens, more data is piled into the `model_analysis_config` JSON column. Old `embedded_settings_detected`, old `slicer_results`, old `geometry` — they all accumulate with no cleanup.

**What to do (step by step):**
1. Define a fixed schema: a Python dictionary that lists every allowed key in `model_analysis_config`.
2. Every time you write to this column, first strip out any key that isn't in the schema.
3. Move large data like slicer results and geometry into the `ProductAnalysisRun` table (from Issue 6) or into separate files referenced by asset rows. Don't store them on the product row.
4. Add a cleanup migration that prunes old keys from existing rows.

### Issue 43 — Cost Formula Version Not Semantic Or Dated Properly

**What's wrong:** The cost formula version is something like `"2026-06-26.product-studio-v1"` — it's not semantic versioning. You can't tell if a change is a breaking change, a new feature, or a bug fix.

**What to do (step by step):**
1. Change `COST_FORMULA_VERSION` to use semantic versioning: `"1.0.0"`.
2. Define a rule: increment MAJOR (1.0.0 → 2.0.0) when existing snapshots would give different results; increment MINOR (1.0.0 → 1.1.0) when new inputs are added; increment PATCH (1.0.0 → 1.0.1) for bug fixes that don't change the formula.
3. Store this version string in every `CostSnapshot`.
4. Write a service function `recalculate_snapshot(snapshot_id)` that can re-run the old formula for old snapshots if the version has changed.

---

## Phase 1: Launch Gate & Create Flow Integrity

**Goal:** Ensure no incomplete product can accidentally go live, and no blocked edit can silently persist changes to the database.

### Issue 1 — Launch Gate Failure Currently Can Persist Blocked Edits

**What's wrong:** When you edit a product and the launch gate says "stop, this product isn't ready to go live," the route still saves your changes to the database before showing you the error. That's like letting you paint a room before checking if the wall is even yours to paint.

**What to do (step by step):**
1. In the `studio` route, before calling `form.populate_product(product)`, first check: "Is this an edit that's trying to make the product active or public?"
2. If yes, copy the form data into a temporary/staging object (not the real product in the database). Run launch gate against the staging object.
3. If launch gate blocks, return the error page WITHOUT calling `db.session.commit()` — add `db.session.rollback()` so any dirty changes are thrown away, then reload the product from the database cleanly.
4. Find `_render_studio()` and remove any `db.session.commit()` call that's not absolutely necessary. If checklist defaults or photo records need to be created on first render, isolate those writes in a separate function that only commits those specific rows.
5. Write tests: edit a product to `active` with missing readiness items → response is blocked (400). Product in database is unchanged. No `product.updated` audit event is recorded.

### Issue 2 — Create Flow Bypasses Launch Gate

**What's wrong:** When creating a brand-new product, you can set it to `active` or `is_public=True` right away. The launch gate only runs during edit, not during creation. New products can go live with no price, no model, no license.

**What to do (step by step):**
1. In the create-product route, add the same launch gate check that exists in the edit route.
2. Change the default status for new products to `draft` — force the user to consciously publish later.
3. If a user tries to create a product as `active` or `is_public=True`, the launch gate runs. If it blocks, either force the product to `draft` silently with a flash message, or return a validation error.
4. Add a text field for "override reason" — if the user provides a 10+ character explanation, the launch gate can be bypassed. Log the override in the audit log.
5. Update the template to clearly say "New products start as Draft. You can publish after adding a model, price, license, and photo."
6. Write tests: creating product as active with missing items fails or forces draft. Creating with valid override reason works and audits the override.

### Issue 42 — `ProductLaunchChecklistItem` `override_reason` Not Validated

**What's wrong:** You can type " " (a space) or "lol" as the override reason and the launch gate will accept it.

**What to do (step by step):**
1. In the form, add a `Length(min=10)` validator to the `launch_override_reason` field.
2. In the `launch_gate()` function, add the same check server-side so it can't be bypassed by sending raw API data.
3. Write a test: empty override is rejected. 9-character override is rejected. 10+ character override is accepted.

### Issue 48 — No Test For Launch Gate Blocking Persistence

**What's wrong:** There's no test that proves Issue 1 is actually fixed.

**What to do (step by step):**
1. Write a test: create a product as draft, try to edit it to active with missing readiness items, assert the response is 400, assert the product in the database is STILL draft, assert no audit event was created for the blocked change.

### Issue 55 — `launch_override_reason` Textarea Has No Max Length

**What's wrong:** You can paste a 10,000-character novel into the override reason field. This takes up space and could be used to store bad content.

**What to do (step by step):**
1. Add `Length(max=2000)` validator to the `launch_override_reason` field in `ProductStudioForm`.
2. When populating the form from the model, strip and truncate the value to 2000 characters.
3. Write tests: 3000 characters is rejected, 2000 characters is accepted.

---

## Phase 2: Model Upload & Analysis Core

**Goal:** Uploading a 3D model, analyzing it, and getting back reliable filament grams, print time, and geometry data — without lies, silent failures, or race conditions.

### Issue 4 — Celery Queue Failures Produce Partial Success Or 500s

**What's wrong:** The code checks `if celery is not None` but Celery always imports as an object (never None), so the check never works. If Redis is down, `.delay()` throws an error after the model file is already saved. The user sees "upload failed" but the file is actually saved. Confusing.

**What to do (step by step):**
1. Replace `if celery is not None` with a real health check: try to ping Redis or inspect Celery's broker connection.
2. Wrap every `.delay()` call in `try/except`:
   - If the queue is unavailable, catch the exception.
   - Set the product's `analysis_status` to `failed`.
   - Set `analysis_error` to a friendly message like "Background worker is not running. Please contact an administrator or try again later."
   - Audit the event with action `model_analysis.enqueue_failed`.
   - Return a JSON response to the browser with `{success: false, error: "Worker unavailable"}`.
3. Create a config option `ANALYSIS_SYNC_MODE` that only enables synchronous (inline) analysis in development/testing, never in production.
4. Do the same for cost-calculation enqueue: wrap in try/except, return controlled error.
5. Write tests: mock `.delay()` to raise an exception, verify the upload route returns controlled JSON and the product status is not left as `pending`.

### Issue 5 — Failed Analysis Tasks Look Successful To The Browser

**What's wrong:** When analysis fails (e.g., the model can't be sliced), the Celery task returns `{"success": False}` but Celery records the task state as `SUCCESS` (because the function finished without crashing). The browser sees `state === "SUCCESS"` and says "Model analysis complete!" even though it actually failed.

**What to do (step by step):**
1. In `studio.js`, change the task-status polling code to inspect `result.success` after checking `state`.
2. If `result.success === false`, show a red failure message in the UI and DO NOT say "Analysis complete."
3. Create a consistent task result envelope that ALL tasks return:
   ```json
   {"success": true, "data": {...}, "error": ""}
   // OR
   {"success": false, "data": null, "error": "What went wrong"}
   ```
4. Update analysis, conversion, cost, and PMP tasks to all use this same envelope.
5. Make sure `analysis-error` contains enough detail for the UI to show a useful message.
6. Write a test: mock a failed analysis task, verify the API returns `{success: false}`, verify the status endpoint communicates the error.

### Issue 8 — Supported File Types Are Misleading

**What's wrong:** The upload form accepts `.stl`, `.glb`, `.gltf`, `.3mf`, and `.obj`. But PrusaSlicer can't actually slice GLB or GLTF reliably. The UI implies every accepted file will give you filament/time estimates, but GLB/GLTF will fail.

**What to do (step by step):**
1. Split the accepted file list into two categories:
   - **Quotable formats** (guaranteed to work with the slicer): `.stl`, `.3mf`, `.obj`
   - **Preview-only formats** (can be viewed but not sliced): `.glb`, `.gltf`
2. In the upload modal, add a note next to preview-only types: "This format can be uploaded for reference/display but cannot be analyzed for filament usage or print time."
3. In the server validation, when a preview-only format is uploaded, skip the slicing task entirely. Don't pretend it can be analyzed.
4. Update all UI copy and documentation to match.
5. Write tests: uploading a preview-only format returns a clear "preview only, no analysis" message. Uploading an unsupported quotable format returns a validation error.

### Issue 9 — Upload Settings Are Stored But Not Fully Honored

**What's wrong:** The upload modal has fields like Copies, Scale %, Preserve Orientation, Multicolor, Nozzle Diameter, Material, etc. But many of these are never passed to PrusaSlicer or applied to the geometry. The UI makes the user think these settings matter, but they don't.

**What to do (step by step):**
1. For EVERY setting in the upload modal, decide: implement it, remove it, or disable it with clear "this setting doesn't affect quoting" text.
2. **Scale %**: Before analysis, scale the model geometry using `trimesh` so that volume, bounds checking, and slicing all use the scaled size.
3. **Copies**: Decide the meaning. If copies = "arrange N on one plate and divide cost by N" (PMP approach), then slice 1 copy, have PMP arrange N, and store per-unit cost as plate_cost / N. If PrusaSlicer CLI doesn't support `--copies` for FFF, don't pass it to the slicer — do it in post-processing.
4. **Preserve Orientation**: Implement by skipping the `--center` flag in the slicer command so the model stays in its original orientation.
5. **Multicolor / Wipe Tower**: If PrusaSlicer supports flags for wipe towers, pass them. If not, disable the field with a note.
6. **Nozzle Diameter**: Pass `--nozzle-diameter` to PrusaSlicer CLI if supported.
7. **Material / Profile**: Pass the correct `--filament-type`, `--filament-density`, and profile INI file to the slicer.
8. Validate embedded 3MF settings after extraction before they can override form settings.
9. Write tests: unit test proving scale changes parsed geometry. Unit test proving copies produces the correct per-unit or per-plate cost. Command-builder tests proving every visible setting is either honored or intentionally ignored with a documented reason.

### Issue 10 — Material Density And Material Type Are Not Reliable

**What's wrong:** If you select PETG, the density doesn't automatically update to PETG's density (1.27 g/cm³). If a 3MF file embeds a material, the density stays at whatever PLA's default was. Volume-to-grams calculations use the wrong density.

**What to do (step by step):**
1. Create a centralized material definitions dictionary or database table:
   ```python
   MATERIAL_DEFAULTS = {
       "PLA": {"density": 1.24, "default_temp": 215},
       "PETG": {"density": 1.27, "default_temp": 240},
       "ABS": {"density": 1.04, "default_temp": 250},
       "ASA": {"density": 1.07, "default_temp": 260},
       "TPU": {"density": 1.21, "default_temp": 225},
   }
   ```
2. When the material selection changes (in the form or from embedded 3MF), auto-fill the density from this table.
3. Add a `density_source` field that tracks whether density was: `default` (from material table), `embedded` (from 3MF file), or `manual` (user typed it in).
4. A manual override always wins. If manual, never overwrite it.
5. Write tests: PETG/ABS/ASA/TPU defaults are applied correctly. Embedded 3MF material updates density correctly. Manual density override wins over defaults.

### Issue 11 — Geometry Validation May Fail Or Misreport Scene-Based Files

**What's wrong:** `trimesh.load_mesh()` can return a "scene" (multiple meshes) instead of a single mesh. The code tries to access `.volume`, `.area`, `.faces`, `.bounds` directly on the result, but a scene doesn't have those properties — it crashes.

**What to do (step by step):**
1. After loading the model, check if the result is a scene (has `.geometry` property).
2. If it's a scene, merge all meshes into a single combined mesh using `trimesh.util.concatenate()`.
3. If merging fails, record a warning rather than failing completely — the geometry might still be usable even if some properties are approximate.
4. Store dimensions AFTER scale is applied, not before.
5. Write tests: multi-mesh/scene validation path works with a small test fixture.

### Issue 12 — G-code Parsing Coverage Is Too Narrow

**What's wrong:** The G-code parser only recognizes Prusa-style comment formats for filament used and time. Bambu Lab and Orca Slicer use different comment formats. Their G-code files get parsed as having zero grams and zero minutes.

**What to do (step by step):**
1. Collect real G-code output samples from PrusaSlicer, Orca Slicer, and Bambu Studio.
2. Expand the regex patterns to handle all three formats.
3. Record WHICH line/pattern supplied the grams and time — store this evidence.
4. If multiple values are found (e.g., two different lines claiming filament used), choose the most specific one and record why.
5. Write tests with fixture files for Prusa, Orca, and Bambu output. Include edge cases: grams only, cm³ fallback, days+hours+minutes+seconds, missing fields.

### Issue 23 — Slicer Profiles Directory Missing At Runtime

**What's wrong:** The code looks for `.ini` profiles in `app/services/slicer_profiles/` but that directory doesn't exist in the repo. The first attempt to slice fails.

**What to do (step by step):**
1. Create the directory `app/services/slicer_profiles/`.
2. Add minimal PrusaSlicer profile files: `bambu_a1.ini`, `bambu_x1c.ini`, `bambu_p1p.ini`. These are configuration files that tell the slicer what printer settings to use.
3. At app startup, ensure the directory exists (create it if missing).
4. Write an integration test (mocked) that verifies the slicing command is built correctly from one of these profiles.

### Issue 24 — Embedded 3MF Settings Can Silently Override User Selections

**What's wrong:** When you upload a 3MF file, the code automatically uses settings embedded in that file (infill, material, supports, etc.) without telling you. The material changes but the density doesn't update.

**What to do (step by step):**
1. After uploading a 3MF file, extract the embedded settings and SHOW them to the user in a confirmation dialog/modal.
2. The user must click "Apply embedded settings" or "Use my manual settings" before analysis continues.
3. When material changes via embedded settings, auto-update density to the material default (using the centralized table from Issue 10) UNLESS the user has manually overridden density.
4. Log/audit which settings came from embedded vs user-selected.
5. Write tests: embedded settings are detected, shown, require confirmation, density auto-updates on material change.

### Issue 27 — Re-Analyze Doesn't Reset Cost Fields

**What's wrong:** When you click "Re-analyze," the old cost numbers (`parsed_filament_grams`, `estimated_material_cost`, `estimated_profit`, etc.) stay visible until the new analysis finishes. You see stale data and don't know it's stale.

**What to do (step by step):**
1. In the `reanalyze_model` function, also clear these fields: `parsed_filament_grams`, `parsed_print_minutes`, `parsed_material_cost`, `parsed_volume_mm3`, `parsed_surface_area_mm2`, `parsed_triangle_count`, `estimated_material_cost`, `estimated_profit`, `estimated_print_minutes`, `gcode_path`, `converted_model_path`, `convert_status`, `conversion_error`, `model_metadata_path`.
2. Better yet: extract a service function called `reset_product_analysis(product)` that clears all of these in one call.
3. Update the cost cards in the UI to say "Cost is stale — recalculating..." or hide them until the new analysis completes.

### Issue 29 — PrusaSlicer `nozzle_diameter` And `filament_density` Not Passed To CLI

**What's wrong:** `nozzle_diameter` and `filament_density` are stored in the config but never passed as arguments to PrusaSlicer. The slicer uses whatever defaults it has, ignoring what the user selected.

**What to do (step by step):**
1. Check the PrusaSlicer CLI documentation (`prusaslicer --help-fff`) to see if `--nozzle-diameter` and any filament-density flags exist.
2. If supported, add them to the CLI command builder in `model_analysis.py`.
3. If NOT supported by the CLI, remove the fields from the upload form or mark them clearly with "(metadata only — does not affect slicing)".
4. Write a command-builder test that proves these flags are passed or intentionally omitted.

### Issue 30 — Copies And Scale Semantics Are Undefined For Costing

**What's wrong:** The upload form asks for "copies" and "scale %" but nobody knows exactly what they mean for costing. If copies = 3 and scale = 50%, is the cost for one item or three? Is the scale applied before or after slicing?

**What to do (step by step):**
1. **Define the meaning of Copies**: In the PMP post-processing step, arrange N copies on one build plate. Slice 1 copy. Divide the total plate cost by N to get per-unit cost. If PrusaSlicer doesn't support the copies flag in CLI, this is the correct approach.
2. **Define the meaning of Scale**: Apply the scale % to the model geometry using `trimesh` BEFORE sending to the slicer. All calculations (volume, grams, time, fit checks) use the scaled geometry.
3. Update the cost engine: add a `per_unit_cost` calculation that takes plate cost and divides by copies.
4. Store `is_per_unit` flag on the snapshot so it's clear what the numbers represent.
5. Write clear UI copy: "Copies per plate: 3 → each unit costs 1/3 of the plate total."
6. Write tests: copies/scale affect parsed geometry and cost correctly. PMP divides plate cost by copies.

### Issue 31 — `preserve_orientation` And `multicolor` Are UI-Only

**What's wrong:** These two settings are shown in the form but never actually used. The user thinks they're configuring something, but nothing happens.

**What to do (step by step):**
1. For `preserve_orientation`: implement it by conditionally skipping the `--center` flag in the PrusaSlicer command.
2. For `multicolor`: if PrusaSlicer supports `--wipe-tower` or similar flags, implement them. If not, disable the field and add text: "(This feature is not yet supported by the slicer integration.)"
3. Write command-builder tests that prove each setting is honored or explicitly disabled.

### Issue 32 — Missing `trimesh` / PrusaSlicer Runtime Checks In Production Path

**What's wrong:** When `trimesh` can't import or PrusaSlicer is not installed, the Celery task silently fails and retries. There's no startup check. Production deployments can look fine but every analysis task fails.

**What to do (step by step):**
1. Add a startup health check function in `create_app()` (or a CLI command) that:
   - Tries to `import trimesh` and reports success/failure.
   - Runs `prusaslicer --help-fff` and reports success/failure.
2. Store the results as app config flags: `app.config['TRIMESH_AVAILABLE']` and `app.config['PRUSASLICER_AVAILABLE']`.
3. In the Product Studio, show a warning banner: "Analysis is unavailable — PrusaSlicer is not installed on this server."
4. In the Celery task, check these flags first. If dependencies are missing, fail immediately with a non-retryable error and a clear message.
5. Write a test that mocks missing dependencies and verifies the task returns the correct error.

### Issue 37 — PMP Task Uses Hardcoded Printer "u1"

**What's wrong:** The PMP (printability/arrangement) function is called with `printer="u1"` hardcoded. It should use the product's selected printer profile.

**What to do (step by step):**
1. Pass the product's printer profile (from the product settings or associated printer) to the PMP function instead of hardcoding `"u1"`.
2. Store the printer used in the PMP metadata.
3. Write a test: PMP uses the product's printer profile, not the hardcoded value.

### Issue 44 — No Test For Concurrent Analysis Race Condition

**What's wrong:** The race condition described in Issue 6 has zero test coverage.

**What to do (step by step):**
1. Write a test: start analysis run A for a product, start analysis run B for the same product (creating B while A is "running"), complete A after B exists, verify A's results did NOT overwrite B's product fields.

### Issue 45 — No Test For Failed Analysis UI State

**What's wrong:** The false-success UI bug from Issue 5 has no test.

**What to do (step by step):**
1. Write a test: mock a failed analysis task that returns `{"success": false}`, verify the API endpoint correctly reports failure, and verify that a frontend integration test would show the error state.

### Issue 49 — Missing Slicer Profiles — Startup Failure

**What's wrong:** Without slicer profile `.ini` files, any slicing attempt fails on startup.

**What to do (step by step):**
1. Same as Issue 23 — add the profiles + directory + startup check + test.

### Issue 50 — Re-Analyze Should Be Idempotent And Safe

**What's wrong:** You can click "Re-analyze" while an analysis is already running. This queues a second, duplicate analysis with no warning.

**What to do (step by step):**
1. Before queuing a new analysis, check the product's `analysis_status`.
2. If status is `pending` or `analyzing`, return the current task ID and an error message: "An analysis is already in progress."
3. Optionally, allow a "force re-analyze" that cancels/supersedes the previous task (requires task revocation support).
4. Write a test: calling re-analyze while analysis is running returns the existing task ID or an error, not a duplicate task.

---

## Phase 3: Cost Engine & Snapshots

**Goal:** Cost calculations use the right filament spools, show the right confidence levels, record sufficient evidence, and are fully audited.

### Issue 13 — Filament Cost Uses All Spools Instead Of Matching The Product/Material

**What's wrong:** `_best_spool_match()` averages ALL spools in the database. It doesn't filter by business, material, or color. A PLA product might get PETG costs. A product from Business A might get Business B's costs.

**What to do (step by step):**
1. Replace `_best_spool_match()` with a new function `resolve_material_cost(business_id, material_type, ...)`.
2. Inputs to the resolver:
   - `business_id` (required — always filter by this)
   - `material_type` (required — PLA, PETG, etc.)
   - `color` (optional — if the user selected a color)
   - `spool_id` (optional — if the user explicitly picked a spool)
   - `fallback_policy` (what to do if no exact match)
3. If exact match (same business + same material): use it, confidence = "high".
4. If partial match (same business, different material fallback): use it, confidence = "medium", record fallback reason.
5. If no match at all: confidence = "low" or "none", force `cost_per_gram = 0`.
6. Store in the snapshot: which spools were matched, the weighted average cost per gram, the fallback reason (if any), the material type, and the color.
7. Write tests: two businesses with different spools cannot affect each other's costs. PLA product does not use PETG spool costs. Fallback with no spools is explicit and low-confidence.

### Issue 14 — Product Studio Missing Cost Inputs

**What's wrong:** The Cost Engine uses labor minutes, labor rate, packaging cost, payment fees, market allocation, target margin, and failure rate. But Product Studio only exposes base price and model settings. `estimated_labor_minutes` exists on the Product model but is not shown in the form.

**What to do (step by step):**
1. Add a "Cost Inputs" section to the Product Studio form.
2. Include these fields: `estimated_labor_minutes`, `packaging_cost_override`, `target_margin_percent`, `material_spool_override` (optional spool selection).
3. Next to each field, show the global default value so the user knows what's being assumed: "Global default: 5 min per item | Override: [____]"
4. Decide where these live: put overrides on the Product model (with nullable fields that fall back to global defaults).
5. Write tests: saving cost inputs persists them correctly. Cost calculation uses them. UI renders defaults and saved values.

### Issue 16 — Manual Calculate Cost Can Produce Misleading No-Model Results

**What's wrong:** If analysis is pending or failed, clicking "Calculate Cost" returns `no_model` with zero material/machine cost, but the UI still renders normal-looking cost cards. The user sees "$0.00" for material and thinks that's correct.

**What to do (step by step):**
1. When analysis has not completed, show a warning in the cost cards: "⚠️ No model data — material and machine costs reflect estimates only."
2. Block automatic cost calculation until analysis is complete. If the user wants to estimate without a model, require an explicit confirmation checkbox.
3. Add a "confidence level" badge to the cost cards:
   - **High** (green) = exact spool match with good data
   - **Medium** (yellow) = fallback used
   - **Low** (orange) = no spool data
   - **None** (red) = no model
4. Write tests: pending analysis returns a warning state. No-model calculation cannot silently look like a normal successful cost.

### Issue 17 — Manual Cost Calculation Lacks Audit Coverage

**What's wrong:** When you manually calculate cost, no audit event is recorded. When analysis automatically creates a cost snapshot, no audit event is recorded. Nobody knows who calculated what or when.

**What to do (step by step):**
1. When a manual cost calculation happens, audit: `cost_snapshot.created` with `actor_id` (who did it), `before_state` (previous snapshot ID and values), `after_state` (new snapshot ID and values).
2. When automatic model-analysis creates a cost snapshot, audit: `cost_snapshot.created` with `actor_type="system"`, `metadata={"snapshot_id": ..., "analysis_run_id": ...}`.
3. Write tests: manual cost calculation dispatches audit event. Automatic analysis snapshot dispatches audit event.

### Issue 25 — Cost Confidence Logic Is Flawed

**What's wrong:** The current logic says: confidence = "high" if there's a spool match AND failure rate > 0. This means a perfect spool match with zero failure rate gets "medium" instead of "high". That's backwards.

**What to do (step by step):**
1. Rewrite the confidence logic:
   - **high**: exact material/spool match with cost data for the right business and material
   - **medium**: fallback average used (e.g., same material but different color)
   - **low**: no spool data at all, cost_per_gram is estimated
   - **none**: cost_per_gram = 0, no spool cost available
2. Failure rate should NOT affect confidence — it's a separate calculation.
3. If `cost_per_gram == 0`, force confidence to "none" and set `evidence_source = "no_spool_cost"`.
4. Write tests: high/medium/low/none are assigned correctly based on evidence, not failure rate.

### Issue 38 — Cost Engine `market_allocation` And `payment_fee_rate` Never Exposed In UI

**What's wrong:** The cost engine accepts `market_allocation` (how much of a product's cost is attributed to market booth fees) and `payment_fee_rate` (credit card processing fees), but the Product Studio never asks the user for these values.

**What to do (step by step):**
1. Add optional fields to the Cost Inputs section: "Market/booth allocation ($)" and "Payment fee rate (%)" or "Payment fee ($)".
2. For payment fee rate, use a global default from Settings if no product-level override is given.
3. Pass these values to the cost calculation when creating cost snapshots.
4. Expose them in the API for programmatic access.

### Issue 46 — No Test For Cost Snapshot Evidence Traceability

**What's wrong:** No test proves that cost snapshots actually contain the evidence they should (from Issue 15).

**What to do (step by step):**
1. Write a test: create a cost snapshot and verify it includes model file hash, analysis run ID, slicer settings, material, density.

### Issue 47 — No Test For Filament Cost Business/Material Isolation

**What's wrong:** No test proves Issue 13 is fixed.

**What to do (step by step):**
1. Write a test: create two businesses, each with different filament spools (Business A: PLA at $20/kg, Business B: PETG at $30/kg). Calculate cost for a PLA product in Business A. Verify it uses PLA $20/kg — NOT Business B's PETG $30/kg.

---

## Phase 4: UI, UX & User Feedback

**Goal:** Users see clear error messages, form validation works, progress is visible, upload limits make sense, memory usage is reasonable, and images are validated and audited.

### Issue 3 — Validation Errors Are Silent Or Hard To See

**What's wrong:** When a form has an error, the page returns HTTP 200 (not 400) and errors aren't shown next to the fields. The user doesn't know what they did wrong.

**What to do (step by step):**
1. In the `studio` route, return HTTP 400 when form validation fails, not 200.
2. In the template, add error-display code next to each field:
   ```jinja
   {% if form.sku.errors %}
     <ul class="text-red-500 text-sm mt-1">
       {% for error in form.sku.errors %}
         <li>{{ error }}</li>
       {% endfor %}
     </ul>
   {% endif %}
   ```
3. Add an error summary banner at the top of the form: "Please correct the errors below."
4. Preserve the user's input when the page re-renders with errors (WTForms does this automatically, but make sure the route sends back the form with the POST data).
5. If no categories exist, show a helpful message: "No categories found. Create one first." with a link to the category management page.
6. Handle duplicate slug/SKU in the form validator (not just the database) so the user gets a clear error message before the 500 error.
7. Write tests: invalid POST returns 400. Error text appears in response. Duplicate slug/SKU returns validation error.

### Issue 18 — Product Studio AJAX Updates Do Not Refresh Readiness

**What's wrong:** After analysis or costing completes, the metric cards update but the readiness score and checklist still show the old state. The user thinks the model isn't analyzed yet.

**What to do (step by step):**
1. After analysis finishes successfully and conversion (if applicable) completes, add `location.reload()` to refresh the full page so all readiness state is current.
2. Alternative: fetch and re-render only the readiness/checklist partials via HTMX or AJAX. The simplest correct approach is `location.reload()`.
3. Write a test: simulate analysis completion and verify the readiness state in the HTML shows "analyzed" and "cost calculated."

### Issue 19 — Progress State Needs A Real State Machine

**What's wrong:** Different tasks use different status names. Failed validation can look complete. Timeout shows a confusing message.

**What to do (step by step):**
1. Standardize ALL task statuses to this list: `queued`, `started`, `validating`, `slicing`, `storing_gcode`, `costing`, `converting`, `complete`, `failed`, `superseded`.
2. Use the same JSON envelope for every status endpoint:
   ```json
   {"success": true, "status": "slicing", "data": {...}, "error": ""}
   ```
3. In the UI, when status is `failed`, show a red error message with a "Retry" button.
4. When status is `superseded`, show "This analysis was superseded by a newer upload."
5. Write backend tests for the status envelope format.

### Issue 20 — Upload Size Limits Conflict

**What's wrong:** The UI says "up to 256 MB," the form allows 256 MB, but Flask's `MAX_CONTENT_LENGTH` defaults to 16 MB. Any file over 16 MB is rejected before the form even runs.

**What to do (step by step):**
1. Decide on ONE upload limit for model files. 256 MB is reasonable for 3D models.
2. Update `MAX_CONTENT_LENGTH_MB` in `config.py` to 256 (or add a separate `MAX_MODEL_UPLOAD_SIZE` config).
3. Update `.env.example` to include the new value.
4. Make sure the form validator, UI text, and config all agree on 256 MB.
5. Handle the HTTP 413 error (Request Entity Too Large) with a friendly JSON response (for AJAX uploads) or a friendly HTML page (for regular form posts).
6. Write tests: file over the limit returns clear 413/400 behavior. UI copy reflects the real limit.

### Issue 21 — Uploads Read Large Files Into Memory

**What's wrong:** The upload code calls `file.read()` which loads the entire file (up to 256 MB) into memory. Then hashing also works on the full bytes. For multiple large files, this can crash the server.

**What to do (step by step):**
1. Stream the uploaded file to storage (file system or S3) in chunks — never load the whole thing into memory at once.
2. Compute the SHA256 hash while streaming using `hashlib.sha256().update(chunk)` in the loop.
3. Only store the hash and file size — never keep the full bytes in a variable unnecessarily.
4. Write a test: prove the uploaded file's hash and size are correct without needing a huge fixture.

### Issue 22 — Product Images Are Under-Validated And Under-Audited

**What's wrong:** Image uploads only check the file extension (`.jpg`, `.png`). You could rename `virus.exe` to `photo.jpg` and it would be accepted. There's no size limit for images, and no audit events for image operations.

**What to do (step by step):**
1. Create a new form/validator for image uploads with:
   - Allowed extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
   - Content-type check: verify the file's MIME type matches
   - File size limit: 5 MB for product images
   - Magic-byte / header check: use `imghdr` or `PIL/Pillow` to verify the file is actually an image
2. Audit every image action: upload, set as default, set as POS image, delete.
3. Write tests: unsafe extension rejected. Oversized image rejected. File renamed from `virus.exe` to `photo.jpg` is rejected by content validation. Audit events recorded.

### Issue 28 — No Request-Too-Large Handling For Oversized Uploads

**What's wrong:** When a file exceeds `MAX_CONTENT_LENGTH`, Flask returns a generic browser error page (413). There's no custom handler.

**What to do (step by step):**
1. Register a custom error handler for HTTP 413 in Flask:
   ```python
   @app.errorhandler(413)
   def request_entity_too_large(error):
       if request.is_xhr or request.headers.get('Accept') == 'application/json':
           return jsonify({"error": "File too large"}), 413
       return render_template("errors/413.html"), 413
   ```
2. Make sure the custom page includes the actual limit and suggests compressing or using a smaller file.

### Issue 33 — Product Create Doesn't Validate Category Exists Before Form Render

**What's wrong:** The product form loads categories from the database. If there are zero categories, the dropdown is empty but the field is required. The user can't submit but gets no explanation.

**What to do (step by step):**
1. In the `studio` route's GET handler, check if any categories exist.
2. If none exist: flash a warning "You need at least one category before you can create a product" and redirect to the category management page, or show a prominent message on the form with a link to create a category.
3. Make the form handle zero-category state gracefully.

### Issue 34 — Image Upload Uses `file.read()` Without Size Limit

**What's wrong:** Same as Issue 21 but specifically for image uploads — `file.read()` loads the whole image into memory with no per-image size limit.

**What to do (step by step):**
1. Add a `FileSize` validator to the image upload form (max 5 MB).
2. Stream the image to storage instead of reading it all into memory.
3. Validate the image content using Pillow before committing.
4. Audit the action. (This is covered by Issue 22's fix.)

### Issue 35 — Readiness/Checklist Not Refreshed After AJAX Analysis/Costing

**What's wrong:** Same as Issue 18. Include it here so it's not lost.

**What to do (step by step):**
1. Same fix as Issue 18: `location.reload()` after successful analysis + conversion. Or update partials.

### Issue 36 — Task Status Envelope Inconsistent Between Routes

**What's wrong:** `/task-status` returns `{state, result, error, traceback, info}`. The analysis task returns `{"success": True/False}` inside result. The cost task returns a breakdown dict inside result. The frontend has to handle all three formats differently.

**What to do (step by step):**
1. Standardize ALL task result envelopes to:
   ```json
   {"success": true, "data": {...}, "error": ""}
   ```
2. Update `/task-status` endpoint to wrap Celery results into this envelope.
3. Update `studio.js` to check `data.success` (not just `state === "SUCCESS"`).
4. Cover: analysis task, conversion task, cost task, PMP task.

### Issue 41 — No Audit For `model_analysis.completed` vs `model_analysis.failed` Distinction

**What's wrong:** Both success and failure are logged as "model_analysis" events, but you can't easily search for successes vs failures.

**What to do (step by step):**
1. Add an `outcome` field to the audit event metadata: `"outcome": "success"` or `"outcome": "failure"`.
2. Make sure all analysis audit events include this field.
3. Use consistent action names: `model_analysis.completed` (only for success) and `model_analysis.failed` (only for failure).

---

## Phase 5: Security & Hardening

**Goal:** No CSRF bypasses, no rate-limit bypasses, no cross-business data leaks, no malicious URLs in model_source_url.

### Issue 51 — AJAX Endpoints Lack CSRF Enforcement For Fetch Requests

**What's wrong:** The JavaScript sends `X-CSRFToken` header on every fetch, but the server doesn't validate it for AJAX requests. An attacker's website could make a cross-origin POST that passes the session cookie but lacks the token.

**What to do (step by step):**
1. Enable `WTF_CSRF_CHECK_DEFAULT = True` in Flask config (if not already).
2. Create a decorator `@csrf_protect_api` that reads the `X-CSRFToken` header from the request and validates it against the session token. Return 403 if missing or invalid.
3. Apply this decorator to ALL mutation endpoints used by JavaScript: `upload-model`, `reanalyze`, `calculate-costs`, `upload-image`, `set-default-image`, `set-pos-image`, `delete-image`, `delete-asset`, `update-checklist`, `retire-product`, etc.
4. Make sure the 413 error handler also returns a valid CSRF context so there's no bypass there.
5. Write tests: POST to upload-model without `X-CSRFToken` returns 403. POST with invalid token returns 403.

### Issue 52 — No Rate Limiting On Product Mutation Endpoints

**What's wrong:** A user or script can hammer `upload-model` and `calculate-costs` thousands of times per minute, degrading the Celery queue and storage.

**What to do (step by step):**
1. Install Flask-Limiter or add a custom rate-limiting decorator.
2. Apply sensible limits:
   - `upload-model`: 60 requests/minute
   - `reanalyze`: 30 requests/minute
   - `calculate-costs`: 30 requests/minute
   - `upload-image`, `set-default-image`, `set-pos-image`: 120 requests/minute combined
   - `delete-asset`, `delete-image`: 60 requests/minute
   - `update-checklist`: 120 requests/minute
3. Return HTTP 429 with a `Retry-After` header and a friendly message: "Too many requests. Please wait X seconds."
4. Write tests: rapid requests trigger 429 after the limit. Rate limit resets after window expires.

### Issue 53 — No Business/Ownership Check On Product Routes

**What's wrong:** Any ADMIN or STAFF user can edit any product, even from a different business. In a multi-business setup, Business A could modify Business B's product data.

**What to do (step by step):**
1. In every product route (studio, upload, reanalyze, calculate-costs, image operations, asset operations, retire, delete), add a check: `if product.business_id != current_user.business_id: abort(403)`.
2. For single-business mode, this protects against future data leakage.
3. For destructive operations (retire, delete asset, delete image), require `ADMIN` role.
4. STAFF users can edit non-destructive fields (name, description, price) but not delete or publish.
5. Write tests: STAFF user cannot retire a product. Product from a different business cannot be reached.

### Issue 54 — `model_source_url` Has No URL Validation

**What's wrong:** The `model_source_url` field accepts any text. A user could store `javascript:alert(1)` or `ftp://malicious-server.com` or an internal IP address.

**What to do (step by step):**
1. Add a `URL` validator to the `model_source_url` field in `ProductStudioForm`.
2. Allow only `http://` and `https://` schemes.
3. Optionally add an allowlist of trusted domains (thingiverse.com, printables.com, myminifactory.com, etc.).
4. Store a normalized version of the URL.
5. Write tests: `javascript:` URI is rejected. `ftp://` URI is rejected. Valid HTTPS URL is accepted and normalized.

---

## Post-Phase: Documentation & Verification

### Documentation Updates

Update these files:
1. `docs/product_creation_developer_flow.md` — reflect new tables, race-proofing, asset model, updated validation.
2. `docs/model_analysis_workflow.md` — document status envelope, slotable formats, scale/copies semantics, embedded 3MF flow.
3. `README.md` — update any changed setup commands or config.
4. `.env.example` — update upload limits, Prusa path config, Celery flags, analysis settings.

Each doc must clearly say:
- Which file formats are quotable vs preview-only.
- How scale and copies are interpreted for costing.
- How material/spool cost is selected.
- What happens when Celery or PrusaSlicer is unavailable.
- How to recover from failed/superseded analysis runs.
- The standard task status envelope.
- How cost confidence levels are determined (high/medium/low/none).
- How embedded 3MF settings are handled and confirmed.
- How to override filament cost per product.
- Semantic versioning for cost formula.

### Verification Commands (Run Before Finishing)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -v --tb=long
```

If any command fails due to environment limitations, document the blocker clearly.

---

## Issue Count Reconciliation

| Section | Issue Range | Count |
|---|---|---|
| Phase 0: Data Model & Schema | 6, 7, 15, 26, 39, 40, 43 | 7 |
| Phase 1: Launch Gate & Create Flow | 1, 2, 42, 48, 55 | 5 |
| Phase 2: Model Upload & Analysis | 4, 5, 8, 9, 10, 11, 12, 23, 24, 27, 29, 30, 31, 32, 37, 44, 45, 49, 50 | 19 |
| Phase 3: Cost Engine & Snapshots | 13, 14, 16, 17, 25, 38, 46, 47 | 8 |
| Phase 4: UI, UX & User Feedback | 3, 18, 19, 20, 21, 22, 28, 33, 34, 35, 36, 41 | 12 |
| Phase 5: Security & Hardening | 51, 52, 53, 54 | 4 |
| **Total** | **1–55** | **55** |

All 55 issues from the source prompt are accounted for. Zero omitted.
