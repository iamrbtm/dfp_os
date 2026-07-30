# Product Creation Developer Flow

This document traces the current DFPos code path for creating a new product, uploading a model, deriving filament/time estimates, and costing the item.

It is written for developers. It describes what the user sees, what the browser does, what Flask does, what Celery does, which models are updated, and where the important assumptions and gaps are.

## Source Files

Primary files involved:

- `app/blueprints/products/__init__.py`
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
- `app/services/product_ops.py`
- `app/services/admin_mutations.py`

The products blueprint is registered as `products` with `url_prefix="/products"` in `app/blueprints/products/__init__.py`.

## Prerequisites Before The User Can Add A Product

The request path is protected before the product workflow starts.

- The `products` module must be enabled. The global `before_request` guard maps the `products` blueprint to the `products` module and aborts with `403` if the module is disabled.
- The user must be logged in.
- The user role must be `ADMIN` or `STAFF`. Product Studio routes use `@roles_required(UserRole.ADMIN, UserRole.STAFF)`.
- CSRF protection must pass for submitted forms and AJAX POST requests.
- At least one `Category` must exist for normal product creation, because `ProductStudioForm.category_id` is required and its choices are loaded from the database.
- Model analysis requires the background worker stack to be functional. The route queues a Celery task; the actual slicing/analyzing work happens in `app.tasks.model_analysis.analyze_product_model`.
- Model validation requires `trimesh` to be installed.
- Filament/time estimates require `PrusaSlicer` to be installed or `PRUSA_SLICER_PATH` to point to it.

## High-Level Flow

The product workflow has three main phases.

1. The user opens Product Studio and presses `New`.
2. The user fills out the product record and presses `Save Product`.
3. After the product exists, the user uploads a model, the system analyzes it, and the Cost Engine creates a cost snapshot.

The important design detail is that the model upload section only appears after the product exists. A product must be saved first so the app has a product ID and can store assets under `products/<product_id>/...`.

## Phase 1: User Presses New

User action:

- The user opens Product Studio from the admin navigation or sidebar.
- The user clicks `New` in the Product Studio product list.

Browser/screen behavior:

- The `New` link points to `url_for('products.studio')`, which resolves to `GET /products/studio`.
- The screen shows the `New Product` form.
- The left sidebar lists existing products.
- The model preview, model upload, cost result cards, readiness score, checklist, photo shot list, and image upload sections are hidden because the template only renders those sections inside `{% if product %}`.

Flask/backend behavior:

- `studio(product_id=None)` in `app/blueprints/products/studio_routes.py` handles `GET /products/studio`.
- `product` is `None` because no product ID is provided.
- A new `ProductStudioForm` is created.
- Since the request is `GET`, `form.status.data` is set to `ProductStatus.DRAFT.value`.
- `_render_studio(None, form, "create")` renders `app/templates/products/studio.html`.
- `_render_studio` also queries categories, collections, and the product list for the sidebar.

Important fields visible on the initial product form:

- `name`
- `slug`
- `sku_base`
- `base_price`
- `category_id`
- `collection_id`
- `product_type`
- `status`
- `short_description`
- `description`
- `is_public`
- `is_pos_visible`
- `is_featured`
- `license_status`
- `design_source`
- `commercial_license_notes`
- `launch_override_reason`
- `model_source_type`
- `model_source_url`
- `model_designer_name`
- `model_license_type`
- `model_license_expiration`
- `model_commercial_use_allowed`
- `model_notes`

Fields not currently exposed by this form but used later by costing:

- `estimated_labor_minutes`

## Phase 2: User Saves The Product Record

User action:

- The user fills out product details.
- The user presses `Save Product`.

Browser/screen behavior:

- The browser submits the main form as a normal HTML form POST.
- The form action is `url_for('products.studio')` for a new product, so it posts to `POST /products/studio`.

Flask/backend behavior:

- `studio(product_id=None)` receives the `POST`.
- `ProductStudioForm.validate_on_submit()` runs.
- WTForms validates required fields, lengths, numeric ranges, duplicate slug, duplicate SKU, and CSRF.
- If the slug is blank, `validate_slug` auto-generates a slug from the product name.
- If validation fails, Product Studio re-renders in create mode with HTTP `400`.

When validation passes:

- `ensure_default_business()` finds or creates the default business/account.
- A new `Product()` model instance is created.
- `product.business_id` is set to the default business ID.
- `form.populate_product(product)` copies form data onto the SQLAlchemy model.
- `create_admin_resource(product, actor_id=current_user.id)` adds and commits the product.
- `create_admin_resource` records an audit event named `product.created` through `app.services.audit.record_audit_event`.
- On duplicate database errors, the session rolls back and the form re-renders with a duplicate warning.
- On success, Flask flashes `Product created successfully.` and redirects to `GET /products/studio/<product.id>`.

Product fields set at this point:

- Identity and catalog fields: `name`, `slug`, `sku_base`, `business_id`, `category_id`, `collection_id`, `product_type`, `status`.
- Sales/display fields: `base_price`, `is_public`, `is_pos_visible`, `is_featured`, `short_description`, `description`, `tags`.
- Compliance/license fields: `license_status`, `design_source`, `commercial_license_notes`, `model_source_type`, `model_source_url`, `model_designer_name`, `model_license_type`, `model_commercial_use_allowed`, `model_license_expiration`, `model_notes`.
- Care/safety fields: `care_instructions`, `safety_notes`.
- Launch override field: `launch_override_reason`.

Product fields not set by the initial save:

- `model_file_path`
- `analysis_status`
- `parsed_volume_mm3`
- `parsed_surface_area_mm2`
- `parsed_triangle_count`
- `parsed_filament_grams`
- `parsed_print_minutes`
- `parsed_material_cost`
- `gcode_path`
- `converted_model_path`
- `model_metadata_path`
- `estimated_material_cost`
- `estimated_print_minutes`
- `estimated_profit`

## Phase 3: Saved Product Page Loads

User-facing screen behavior:

- The browser follows the redirect to `GET /products/studio/<product_id>`.
- The page now shows the full Product Studio screen for this saved product.
- The model preview area appears.
- The model file card appears with drag/drop upload, `Upload & Analyze`, `Assets`, `Calculate Cost`, and `Calculate Trend Score` buttons.
- The cost cards appear, initially showing whatever is currently stored on the product, often zero for a new product.
- Readiness score, launch checklist, product story card, photo shot list, image upload, and retirement workflow appear.

Flask/backend behavior:

- `studio(product_id)` loads the product with `get_by_id(Product, product_id)`.
- `form.load_from_product(product)` copies database fields into the form.
- `_render_studio(product, form, "edit")` runs.
- `_render_studio` calls `ensure_product_ops_defaults(product)`, which creates default `ProductLaunchChecklistItem` and `ProductPhotoShot` records if they do not exist.
- `_render_studio` calls `sync_launch_checklist(product)` and `calculate_product_readiness(product)`.
- `_render_studio` commits after creating/syncing these operational defaults.

Default launch checklist items created:

- License verified
- Model analyzed
- Cost snapshot
- Product photos
- POS tile
- Public description
- Inventory target
- Market test plan
- Safety and care notes

Default photo shot records created:

- Hero
- Scale in hand
- Color variants
- Close-up
- Packaging
- Booth display
- POS tile

Readiness scoring inputs:

- License/commercial rights
- Model analysis status or G-code presence
- Cost snapshot or material cost
- Product photos or shot-list completion
- Public copy
- Price
- POS/public visibility
- Safety/care notes
- Finished goods inventory

## Phase 4: User Chooses A Model File

User action:

- The user drags a model file onto the drop zone or clicks the drop zone to browse.

Browser/screen behavior:

- `app/static/src/js/studio.js` initializes model upload behavior on `DOMContentLoaded`.
- Clicking the drop zone triggers the hidden file input.
- Dragging a file onto the drop zone assigns it to the hidden file input.
- The drop-zone label changes to the selected filename.
- Supported extensions on the HTML input are `.stl`, `.glb`, `.gltf`, `.3mf`, and `.obj`.

No server request has happened yet. At this point the file only exists in the browser file input.

## Phase 5: User Opens Upload Settings

User action:

- The user presses `Upload & Analyze`.

Browser/screen behavior:

- If no file has been selected, the JavaScript opens the file picker instead.
- If a file is selected, the JavaScript opens the `Model slicing settings` modal.
- The user reviews or changes the slicing inputs.

Upload settings shown in the modal:

- Printer profile: `bambu_a1.ini`, `bambu_x1c.ini`, or `bambu_p1p.ini`
- Material: `PLA`, `PETG`, `ABS`, `ASA`, or `TPU`
- Filament density
- Nozzle diameter
- Layer height
- Walls/perimeters
- Top solid layers
- Bottom solid layers
- Infill percent
- Infill pattern
- Supports
- Brim width
- Copies
- Scale percent
- Preserve uploaded orientation
- Multicolor / wipe tower
- Use embedded 3MF settings
- Convert to GLB for preview
- Retain generated G-code

Developer note:

- These settings are stored on `Product.model_analysis_config`.
- Not all settings are currently passed through to the PrusaSlicer CLI. The slicer command uses layer height, perimeters, top/bottom layers, infill pattern, brim width, infill percent, and support settings. Other fields are stored as metadata/config and may affect parsing or future workflows.

## Phase 6: User Uploads The Model

User action:

- The user presses `Upload with these settings` in the modal.

Browser/screen behavior:

- The JavaScript intercepts the form submit.
- It builds `FormData` from the upload form.
- It disables the submit button and changes text to `Uploading...`.
- It sends `fetch("/products/studio/<product_id>/upload-model", { method: "POST", body: formData, headers: { "X-CSRFToken": ... } })`.

Flask/backend route:

- `upload_model(product_id)` in `app/blueprints/products/studio_routes.py` handles `POST /products/studio/<product_id>/upload-model`.

Backend steps:

- Load the product by ID.
- Validate `ProductModelUploadForm`.
- Reject missing files.
- Enforce allowed file extensions: `stl`, `glb`, `gltf`, `3mf`, `obj`.
- Enforce maximum file size of 256 MB.
- Generate a safe storage filename using a UUID plus the original extension.
- Resolve storage bucket/root from config:
  - `PRODUCT_ASSETS_BUCKET`, default `products`
  - `PRODUCT_ASSETS_PATH`, default `uploads/products`
- Store the file at `products/<product_id>/<uuid>.<ext>` using `upload_bytes_to_storage`.
- Local storage returns an absolute local file path.
- S3 storage returns an `s3://bucket/key` reference.
- Set `product.model_file_path` to the storage reference.
- Set `product.model_convert_to_glb` from the upload form.
- Write all upload/slicer settings into `product.model_analysis_config`.
- Set `product.analysis_status = "pending"`.
- Clear previous analysis/conversion state:
  - `analysis_error = None`
  - `analysis_completed_at = None`
  - `convert_status = None`
  - `conversion_error = None`
  - `converted_model_path = None`
  - `gcode_path = None`
- Set `analysis_requested_at` to the current UTC time.
- Write an initial model metadata JSON file through `write_model_metadata(product, source_bytes=source_bytes)`.
- Commit the database transaction.
- Record audit event `product_model.uploaded`.
- Record audit event `model_analysis.queued`.
- Queue Celery task `analyze_product_model.delay(product.id)` if Celery is available.
- Return JSON containing `success`, `product_id`, `task_id`, and `file_location`.

Important persistence after upload:

- Product row now points at the uploaded model file.
- Product row is marked analysis `pending`.
- A sidecar metadata file is written, but it will not yet contain final filament/time/cost results.

## Phase 7: Browser Shows Live Analysis Progress

Browser/screen behavior after a successful upload response:

- The settings modal closes.
- A flash event says `Model uploaded. Analysis started.`
- The live progress component becomes visible.
- The progress bar moves to `2%` with a queued message.
- If the JSON response contains `task_id`, the browser starts polling `GET /products/studio/task-status/<task_id>` every 1.5 seconds.

Polling behavior:

- `SUCCESS`: call the completion handler.
- `FAILURE`: show a danger flash and update progress as failed.
- `PROGRESS` or `STARTED`: use the returned task metadata to update the progress bar and message.
- `PENDING`: keep polling until timeout.
- Timeout is 120 seconds in `studio.js`.

Operational note:

- If the Celery worker is not running, the browser will usually see `PENDING` until timeout. The upload has still been saved, but the analysis/costing task will not finish until a worker processes it.

## Phase 8: Celery Starts Model Analysis

Background task:

- `analyze_product_model(self, product_id)` in `app/tasks/model_analysis.py` performs the actual analysis.

Backend steps:

- Load the `Product` by ID.
- Emit progress/audit step `model_analysis.started` at 5%.
- Set `product.analysis_status = "analyzing"` and commit.
- Read `product.model_file_path`.
- If the model is in S3, download bytes into a temporary work directory.
- If the model is local, use the local path directly.
- Emit progress/audit step `model_analysis.file_downloaded` at 15%.

Failure behavior:

- If no file exists or the file cannot be loaded, the task sets `analysis_status = "failed"`, stores `analysis_error`, commits, records `model_analysis.failed`, and retries for unexpected exceptions.

## Phase 9: Geometry Validation

Background service:

- `validate_model_file(model_path)` in `app/services/model_analysis.py` validates geometry using `trimesh`.

What the computer calculates:

- File extension / detected format
- Mesh volume in cubic millimeters
- Surface area in square millimeters
- Triangle count
- Whether the mesh is watertight
- Bounding box min/max dimensions
- Width, depth, and height in millimeters
- Whether the model appears to fit the supported Bambu printer build volumes
- A possible scale warning if the largest dimension is under 10 mm, suggesting the model might be in inches rather than millimeters

Database updates after successful validation:

- `product.parsed_volume_mm3`
- `product.parsed_surface_area_mm2`
- `product.parsed_triangle_count`
- `product.model_analysis_config["geometry"]`

3MF embedded settings behavior:

- If the uploaded file is a `.3mf`, `extract_3mf_slicer_settings` attempts to read slicer/project settings from the archive.
- If `use_embedded_settings` is enabled and settings are detected, embedded settings can overwrite upload-modal settings in `model_analysis_config`.
- Examples include infill percent, infill pattern, material type, support mode, and build-plate-only support mode.

Progress/audit:

- After validation, the task commits and emits `model_analysis.validated` at 35%.

Failure behavior:

- If validation fails, `analysis_status` becomes `failed`, `analysis_error` stores the validation error, and the task returns a failure JSON payload.

## Phase 10: Slicing For Filament And Time

Background service:

- `slice_with_prusaslicer(model_path, profile_name=..., output_path=..., slicer_options=...)` in `app/services/model_analysis.py` runs PrusaSlicer.

Backend steps:

- Set `product.analysis_status = "slicing"` and commit.
- Emit `model_analysis.slicing_started` at 45%.
- Build a PrusaSlicer command:
  - Executable from `PRUSA_SLICER_PATH`, default `prusa-slicer`
  - `--export-gcode`
  - `--load <slicer_profile>`
  - `--output <tmp>/quote.gcode`
  - `--center 128,128` for the first attempt
  - Optional CLI flags for layer height, walls, top/bottom layers, infill pattern, brim, infill percent, and supports
  - Uploaded model path
- Before slicing, verify the executable responds to `--help-fff`.
- Run the slicer with a 600 second timeout.
- If centered slicing fails, try again with default profile and no center argument.

What counts as a successful slice:

- PrusaSlicer exits with return code 0.
- It writes a G-code file.
- `_parse_gcode_stats` can find both filament and print time in G-code comments.

How filament is parsed:

- First preference: a G-code comment matching `; total filament used [g] = <number>`.
- Fallback: a G-code comment matching `; filament used [cm3] = <number>`.
- If only cubic centimeters are present, grams are calculated as `cm3 * filament_density`.
- Default density is PLA density `1.24 g/cm3`, unless upload/embedded settings provide another density.

How print time is parsed:

- The parser looks for comments like `; estimated printing time = ...` or `; estimated print time = ...`.
- It parses days, hours, minutes, and seconds into total minutes.
- Example components: `1d`, `3h`, `42m`, `12s`.

Additional parsed value:

- The parser optionally captures total layer count if present.

Database updates after successful slicing:

- `product.parsed_filament_grams`
- `product.parsed_print_minutes`
- `product.parsed_material_cost`

Important material-cost detail:

- `parsed_material_cost` is calculated immediately as `parsed_filament_grams * cost_per_gram`.
- The `cost_per_gram` comes from `_best_spool_match()` in `app/services/cost_engine.py`.
- `_best_spool_match()` currently computes a weighted average cost per gram across all `FilamentSpool` records with `remaining_weight_grams > 0` and `cost_per_gram > 0`.
- It does not currently filter by uploaded material, color, brand, product, or printer.

Progress/audit:

- The task emits `model_analysis.sliced` at 70%.

Failure behavior:

- If both slicing attempts fail, `analysis_status` becomes `failed`.
- `analysis_error` stores the combined slicer errors.
- The task records `model_analysis.failed` with `step = slicing`.
- No filament/time estimates are stored for that run.

## Phase 11: G-code Storage

Condition:

- This only happens if slicing succeeded and `model_analysis_config["retain_gcode"]` is true. The upload form defaults this to true.

Backend behavior:

- The generated G-code is uploaded to product asset storage.
- The preferred filename is based on the product slug/name, for example `<product-slug>.gcode`.
- `product.gcode_path` is set to the storage reference.
- The task emits `model_analysis.gcode_stored` at 80%.

Failure behavior:

- Failure to store G-code is logged as a warning, but does not fail the entire analysis task.

## Phase 12: Automatic Initial Cost Snapshot

Background helper:

- `_apply_initial_cost_snapshot(product)` in `app/tasks/model_analysis.py` runs after slicing succeeds.

Backend behavior:

- Set `product.analysis_status = "complete"`.
- Set `product.analysis_completed_at` to current UTC time.
- Store slicer stats under `product.model_analysis_config["slicer_results"]`.
- Call `calculate_product_cost(product=product)`.
- Copy high-level cost fields back onto the product:
  - `product.estimated_material_cost = breakdown.material_cost`
  - `product.estimated_profit = breakdown.margin_dollars`
  - `product.estimated_print_minutes = round(breakdown.print_minutes)`
- Call `persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="model_analysis.product")`.
- Write updated model metadata JSON through `write_model_metadata(product)`.
- Commit the transaction.
- Emit `model_analysis.costed` at 90%.
- Record `model_analysis.completed` at 100%.

Cost snapshot behavior:

- Existing non-stale cost snapshots for the product are marked `stale = True`.
- A new `CostSnapshot` row is inserted.
- The snapshot stores input JSON and output JSON.
- The snapshot points at the selected spool ID returned by `_best_spool_match()`, if one exists.
- The snapshot records formula version `2026-06-26.product-studio-v1`.

Important distinction:

- This automatic snapshot is created by model analysis.
- The visible `Calculate Cost` button can create a later snapshot manually.

## Phase 13: Optional GLB Conversion For Preview

Condition:

- This runs if `product.model_convert_to_glb` is true. The upload form defaults this to true.

Backend behavior:

- After analysis commits, the task queues `convert_product_model_for_viewer.delay(product_id)`.
- The browser receives `convert_task_id` in the analysis task result and polls that task too.
- The conversion task attempts to convert the model to `.glb` using `trimesh`.
- On success, `product.converted_model_path` is set.
- The template uses `product.converted_model_path or product.model_file_path` when serving the model to `<model-viewer>`.

Screen behavior:

- Once conversion completes, the model preview can load the GLB through `GET /products/studio/<product_id>/view-model`.

## Phase 14: Browser Refreshes Analysis Numbers

Browser behavior after analysis completes:

- `studio.js` calls `refreshAnalysisResult(productId)`.
- The browser fetches `GET /products/studio/<product_id>/analysis-result`.

JSON returned by the route:

- `status`
- `error`
- `volume_mm3`
- `surface_area_mm2`
- `triangle_count`
- `filament_grams`
- `print_minutes`
- `material_cost`
- `convert_status`
- `converted_model_path`

Screen updates:

- `Analysis` status card updates to the current status.
- `Print Time` card updates to rounded minutes.
- `Material Cost` card updates to the parsed material cost.

Important UI detail:

- The refresh updates only selected cards. It does not fully reload the page after initial analysis completion.
- Readiness/checklist sections may not visually update until reload unless another action refreshes the page.

## Phase 15: User Clicks Calculate Cost

User action:

- The user presses `Calculate Cost` in the Model File card.

Browser/screen behavior:

- JavaScript intercepts the click on `[data-calc-costs]`.
- The button is disabled and text changes to `Calculating...`.
- The `cost-results` area shows a loading placeholder.
- The browser sends `POST /products/studio/<product_id>/calculate-costs` with CSRF header.

Flask/backend route:

- `calculate_product_costs(product_id)` in `app/blueprints/products/studio_routes.py` handles the request.

Backend behavior when Celery is available:

- Queue `calculate_product_cost_task.delay(product_id)`.
- Return JSON with `success = true` and `task_id`.
- The browser polls the task.
- When the task succeeds, the browser fetches `GET /products/studio/cost-result/<product_id>` for display.

Backend behavior without Celery:

- Run `calculate_product_cost(product=product)` synchronously.
- Update product-level cost fields.
- Persist a cost snapshot with `snapshot_reason="studio.product"`.
- Commit.
- Return cost JSON directly.

Cost task behavior:

- `app/tasks/cost_calculation.py` loads the product.
- Calls `calculate_product_cost(product=product)`.
- Updates product-level fields:
  - `estimated_material_cost`
  - `estimated_profit`
  - `estimated_print_minutes`
- Persists a snapshot with `snapshot_reason="task.product"`.
- Commits.
- Returns the full breakdown as strings.

Screen updates after cost result:

- The `cost-results` area is replaced with four cards:
  - Material Cost
  - Total Cost
  - Margin
  - Print Time
- Button text changes to `Re-Calculate`.

## Cost Engine Calculation Details

Main function:

- `calculate_product_cost(product=product, ...)` in `app/services/cost_engine.py`.

Settings loaded from app settings:

- `cost_engine_labor_rate`, default `18.00`
- `cost_engine_packaging_cost`, default `0.50`
- `cost_engine_failure_rate`, default `0.05`
- `cost_engine_target_margin_percent`, default `55.00`
- `cost_engine_energy_hour_rate`, default `0.18`
- `cost_engine_depreciation_hour_rate`, default `0.22`
- `cost_engine_maintenance_hour_rate`, default `0.06`
- `cost_engine_ams_waste_hour_rate`, default `0.04`

Derived machine hourly rate:

- `energy + depreciation + maintenance + ams_waste`
- With defaults, this is `0.18 + 0.22 + 0.06 + 0.04 = 0.50` per hour.

Model-analysis requirement:

- `_latest_model_analysis(product)` only returns model data when:
  - `product.analysis_status == "complete"`
  - `product.parsed_filament_grams is not None`
  - `product.parsed_print_minutes is not None`

If no completed model analysis exists:

- `filament_grams = 0.00`
- `print_minutes = 0.00`
- `model_volume_cm3 = 0.00`
- `material_cost = 0.00`
- `machine_cost = 0.00`
- `evidence_source = "no_model"`
- `confidence = "none"`
- `failure_rate = 0.0000`
- `failure_adjustment = 0.00`

If completed model analysis exists:

- `filament_grams` comes from `product.parsed_filament_grams`.
- `print_minutes` comes from `product.parsed_print_minutes`.
- `model_volume_cm3` is `product.parsed_volume_mm3 / 1000`.
- `cost_per_gram` comes from `_best_spool_match()`.
- `material_cost = filament_grams * cost_per_gram`.
- `machine_cost = (print_minutes / 60) * machine_hour_rate`.
- `evidence_source = "generated_slice.product"`.
- Failure rate is resolved from product/printer print-job history, printer-model reliability, or the default setting.

Labor cost:

- `labor_minutes = product.estimated_labor_minutes or 0`.
- `labor_cost = (labor_minutes / 60) * labor_rate`.
- Product Studio does not currently expose `estimated_labor_minutes`, so this is often `0` for newly-created products unless another workflow sets it.

Base cost:

- `base_cost = material_cost + labor_cost + machine_cost + packaging_cost + market_allocation`

Failure adjustment:

- If model data exists, `failure_adjustment = base_cost * resolved_failure_rate`.
- If no model data exists, failure adjustment is `0.00`.

Payment fees:

- `payment_fees = price * payment_fee_rate`
- Product Studio calls use the default `payment_fee_rate = 0.00`.

Total cost:

- `total_cost = base_cost + failure_adjustment + payment_fees`

Suggested price:

- `suggested_price = total_cost / (1 - target_margin_percent / 100)`
- With default target margin of 55%, divisor is `0.45`.

Margin/profit:

- `price = sale_price if provided, else product.base_price`
- If price is greater than zero, margin is calculated against the product price.
- If price is zero, margin is calculated against suggested price.
- `margin_dollars = price_for_margin - total_cost`
- `margin_percent = margin_dollars / price_for_margin * 100`
- `profit_per_unit = margin_dollars`
- `profit_per_print_hour = margin_dollars / print_hours` when print time exists.
- `profit_per_market_bin_cm3 = margin_dollars / model_volume_cm3` when model volume exists.

Confidence:

- `none` when no model analysis exists.
- `low` when model analysis exists but no spool cost is available.
- `medium` when model analysis exists with spool cost but no positive resolved failure rate.
- `high` when model analysis exists, a spool cost exists, and the resolved failure rate is positive.

## Filament Inventory Behavior

Important current behavior:

- Adding a product does not deduct filament.
- Uploading/analyzing a model does not deduct filament.
- Calculating cost does not deduct filament.
- Filament grams are an estimate used for quoting/costing.
- Actual filament deduction is expected to happen in print-job or inventory workflows, not in Product Studio creation.

Filament cost source:

- `FilamentSpool` contains `remaining_weight_grams`, `cost_per_spool`, and `cost_per_gram`.
- Costing uses all spools with positive remaining grams and positive cost per gram.
- The weighted average is based on remaining grams.
- The selected spool ID stored on the snapshot is currently the most recently updated candidate, not necessarily the spool whose material/color matches the uploaded model.

## Audit Events In This Flow

Product creation:

- `product.created`

Model upload:

- `product_model.uploaded`
- `model_analysis.queued`

Model analysis task:

- `model_analysis.started`
- `model_analysis.file_downloaded`
- `model_analysis.validated`
- `model_analysis.slicing_started`
- `model_analysis.sliced`
- `model_analysis.gcode_stored`
- `model_analysis.costed`
- `model_analysis.completed`
- `model_analysis.failed` on failure

GLB conversion task:

- Conversion-related progress/failure events are recorded from `app/tasks/model_analysis.py`.

Checklist/readiness updates:

- `product_launch_checklist.updated` when a checklist item is manually changed.
- `product_photo_shot.updated` when a photo shot item is manually changed.

## Error And Edge Cases

Validation and form errors:

- Blank name, missing category, invalid enum values, duplicate slug, duplicate SKU, invalid numeric ranges, or failed CSRF cause form validation failure.
- The product is not created if validation fails.

Upload errors:

- Missing file returns JSON `400`.
- Unsupported extension returns form validation errors as JSON `400`.
- Files over 256 MB are rejected by `ProductModelUploadForm`.

Analysis errors:

- Missing model file fails analysis.
- Missing `trimesh` causes validation failure.
- Model loading failures are stored in `product.analysis_error`.
- Missing PrusaSlicer or invalid `PRUSA_SLICER_PATH` causes slicing failure.
- PrusaSlicer timeout after 600 seconds causes slicing failure.
- If G-code cannot be parsed for both filament and time, slicing is treated as failed.

Costing edge cases:

- If no filament spools have usable `cost_per_gram`, material cost is zero and confidence is low when model data exists.
- If model analysis is not complete, cost calculation returns a no-model breakdown with zero material and machine cost.
- If base price is zero, margin is calculated against suggested price instead of product price.
- Product Studio does not currently collect labor minutes, so labor cost will usually be zero for a new product.
- Product Studio default `payment_fee_rate` is zero, so card/payment fees are not included in product-level costing.

Operational edge cases:

- If the Celery worker is not running, upload succeeds but analysis remains pending until a worker processes the queued task.
- The browser times out polling after 120 seconds, but the task may still continue in the background.
- The UI refresh after analysis updates only selected metric cards; checklist/readiness may need a full page reload to reflect new analysis/cost status.

## Developer Sequence Diagram

```text
User
  clicks Product Studio > New

Browser
  GET /products/studio

Flask products.studio
  builds ProductStudioForm
  renders products/studio.html in create mode

User
  fills product fields
  clicks Save Product

Browser
  POST /products/studio

Flask products.studio
  validates ProductStudioForm
  ensure_default_business()
  Product()
  form.populate_product(product)
  create_admin_resource(product)
  audit product.created
  redirect /products/studio/<product_id>

Browser
  GET /products/studio/<product_id>

Flask products.studio
  loads Product
  loads form from product
  ensure_product_ops_defaults(product)
  sync_launch_checklist(product)
  calculate_product_readiness(product)
  renders products/studio.html in edit mode

User
  selects model file
  clicks Upload & Analyze
  confirms slicing settings
  clicks Upload with these settings

Browser studio.js
  FormData(model file + settings)
  POST /products/studio/<product_id>/upload-model

Flask upload_model
  validates file
  stores file under products/<product_id>/...
  updates Product.model_file_path
  stores Product.model_analysis_config
  sets analysis_status=pending
  writes metadata JSON
  audit product_model.uploaded
  audit model_analysis.queued
  queues analyze_product_model Celery task
  returns task_id

Browser studio.js
  polls /products/studio/task-status/<task_id>
  updates progress bar

Celery analyze_product_model
  loads Product
  sets analysis_status=analyzing
  downloads/materializes model
  validate_model_file with trimesh
  stores geometry fields
  extracts embedded 3MF settings if present
  sets analysis_status=slicing
  runs PrusaSlicer
  parses G-code for filament grams and print minutes
  stores parsed_filament_grams and parsed_print_minutes
  stores parsed_material_cost
  optionally stores G-code
  sets analysis_status=complete
  calculate_product_cost(product)
  persist_cost_snapshot(..., reason=model_analysis.product)
  updates estimated_material_cost, estimated_profit, estimated_print_minutes
  writes final metadata JSON
  optionally queues GLB conversion
  returns result

Browser studio.js
  refreshes /products/studio/<product_id>/analysis-result
  updates material cost, print time, analysis status cards

User
  optionally clicks Calculate Cost

Browser studio.js
  POST /products/studio/<product_id>/calculate-costs
  polls task if needed
  fetches /products/studio/cost-result/<product_id>
  updates cost result cards
```

## Current Implementation Gaps To Know About

These are not necessarily bugs, but they are important when working on this flow.

- Filament material/color chosen in the upload modal is stored in config but is not used to choose filament spool cost.
- Costing uses a weighted average across all usable filament spools.
- Product Studio does not expose `estimated_labor_minutes`, even though the Cost Engine uses it.
- The upload route has no synchronous analysis fallback if Celery is absent; it only queues when Celery is available.
- Cost recalculation can run synchronously without Celery, but if analysis has not completed it produces a no-model/zero-material breakdown.
- Product readiness/checklist state is synced on page render, not automatically after every AJAX analysis update.
- Product creation and costing do not create finished-goods inventory records.
- Product creation and costing do not deduct filament inventory.
- `copies`, `scale_percent`, `multicolor`, and several other upload settings are preserved in metadata but are not fully wired into the current PrusaSlicer command.
