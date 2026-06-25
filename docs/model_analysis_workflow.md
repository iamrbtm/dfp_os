# Model Analysis Workflow

From file upload to finished cost calculation — what the program does at each step.

---

## 1. User drops a file on a drop zone

**What happens:**
- The drop zone (product-level or variant-level) captures the file
- `initModelUpload()` or `initVariantModelUpload()` in `studio.js` handles the click/drag-and-drop
- The file input's `change` event updates the drop zone label with the filename

## 2. User clicks "Upload" / "Upload for Variant"

**What happens:**
- JS builds a `FormData` with the file, title, source type, license info, and optional `variant_id`
- `fetch` POSTs to `/products/studio/{product_id}/upload-model`
- The button is disabled and shows "Uploading..."

## 3. Flask route `upload_model()` validates and saves

**File: `app/blueprints/products/studio_routes.py:132-195`**

What happens:
1. Validates the `ModelAssetUploadForm` (file type, size, required fields)
2. Generates a UUID filename (`{uuid}.stl`)
3. Reads the file bytes
4. Uploads to storage via `upload_bytes_to_storage()`:
   - S3 mode → uploads to SeaweedFS bucket `products`
   - Local mode → saves to `uploads/products/{product_id}/{uuid}.stl` for product-level files or `uploads/products/{product_id}/variants/{variant_id}/{uuid}.stl` for variant files
5. Creates a `ModelAsset` DB row with:
   - `status = "pending"`
   - `analysis_status = "pending"`
   - `variant_id` = the variant ID if uploading for a variant
   - `related_product_id` = the product ID
6. Dispatches Celery task `analyze_model_asset.delay(asset_id)`
7. Returns JSON `{asset_id, task_id}` to the browser

## 4. Browser starts polling

**File: `app/static/src/js/studio.js:290-324`** (`pollTask()`)

- Polls every 1.5 seconds via `GET /products/studio/task-status/{task_id}`
- Shows flash messages: "Model uploaded. Analysis started."
- Continues until task state is `SUCCESS` or `FAILURE`
- Timeout after 120 seconds

## 5. Celery task `analyze_model_asset` runs

**File: `app/tasks/model_analysis.py:20-146`**

### 5a. Status → "analyzing"

- Sets `asset.analysis_status = "analyzing"`
- Downloads the model file from storage to a temp directory

### 5b. Validation with trimesh

**File: `app/services/model_analysis.py:64-141`** (`validate_model_file()`)

- Loads the model with trimesh
- Calculates: volume (mm³), surface area (mm²), triangle count
- Checks if the mesh is **watertight** (no holes)
- Calculates bounding box dimensions
- Checks if the model fits on the printer bed (256mm³)
- Detects inch-scale models (largest dimension < 10mm → suggests 25.4x scaling)
- Saves validation results to the asset record (`parsed_volume_mm3`, `parsed_surface_area_mm2`, `parsed_triangle_count`)
- If validation fails → status = "failed", returns error

### 5c. Status → "slicing"

- Sets `asset.analysis_status = "slicing"`

### 5d. Attempt 1: PrusaSlicer with centering

**File: `app/services/model_analysis.py:144-222`** (`slice_with_prusaslicer()`)

- Runs: `prusa-slicer --export-gcode --load {profile} --output {gcode} --center 128,128 {model.stl}`
- Profile: `bambu_a1.ini` (default) — 0.4mm nozzle, 0.2mm layer height, 20% infill, PLA
- `--center 128,128` positions the model in the center of the 256mm³ bed
- Timeout: 600 seconds

### 5e. Attempt 2: PrusaSlicer without centering

If Attempt 1 fails (no G-code produced): retry without `--center` flag. Some models with odd geometry fail when centering is applied.

### 5f. Parse G-code

**File: `app/services/model_analysis.py:228-289`** (`_parse_gcode_stats()`)

- Reads the last 500 lines of the G-code file
- Extracts `total filament used [g]` — if 0.00, falls back to `filament used [cm3]` × 1.24 (PLA density)
- Extracts `estimated printing time (normal mode)` — parses `Xh Ym Zs` format
- If both found → success, returns `{filament_grams, print_minutes}`

### 5g. Calculate material cost

- Default cost per gram: $0.025 (overridable via `cost_engine_cost_per_gram` setting)
- `material_cost = filament_grams × cost_per_gram`

### 5h. Save results

- `parsed_filament_grams` — e.g. 70.97 (g)
- `parsed_print_minutes` — e.g. 349.22 (min)
- `parsed_material_cost` — e.g. $1.77
- `analysis_status = "complete"`
- Propagates `print_minutes` to `product.estimated_print_minutes`

### 5i. Dispatch conversion task

- Dispatches `convert_model_asset_for_viewer.delay(asset_id)`
- Converts the model to GLB format for the 3D viewer

## 6. Conversion task `convert_model_asset_for_viewer`

**File: `app/tasks/model_analysis.py:155-213`**

- If file is already `.glb` → uses it directly
- Otherwise, loads with trimesh and exports as GLB
- Uploads the converted GLB back into the same product or variant folder as the source asset
- Sets `converted_model_path` and `convert_status = "complete"`

## 7. Browser detects task completion

- `pollTask()` sees state = `SUCCESS`
- Calls `location.reload()` to refresh the page

## 8. Page reload renders the 3D preview

**File: `app/templates/products/studio.html`**

- Template renders `<model-viewer>` with `src` pointing to `view_model` endpoint
- Model viewer shows the 3D model with orbit controls and auto-rotate

## 9. Cost Calculation (separate step, user clicks "Calc Cost")

**File: `app/services/cost_engine.py:60-110`** (`calculate_product_cost()`)

1. Calls `_latest_model_analysis(product, variant)`:
   - If variant has model assets → uses the most recently analyzed one
   - If variant has no model assets → falls back to product-level model assets
2. Gets `filament_grams` and `print_minutes` from model analysis (preferred) or from cached variant values
3. Calculates material cost: `filament_grams × cost_per_gram`
4. Calculates labor cost: `(labor_minutes / 60) × labor_rate`
5. Calculates machine cost: `(print_minutes / 60) × machine_hour_rate`
6. Calculates packaging cost (default $0.50)
7. Calculates failure adjustment: `base_cost × failure_rate` (default 5%)
8. Calculates payment fees (default 0%)
9. `total_cost = material + labor + machine + packaging + failure + fees`
10. `suggested_price = total_cost / (1 - target_margin_percent/100)`
11. Returns `CostBreakdown` with all values

## 10. Task saves results back to variant record

**File: `app/tasks/cost_calculation.py:84-128`** (`calculate_variant_cost_task()`)

- `variant.material_cost = breakdown.material_cost`
- `variant.estimated_filament_grams = round(breakdown.filament_grams)`
- `variant.estimated_print_minutes = round(breakdown.print_minutes)`
- Commits to database

## 11. Browser reloads to show updated variant row

---

## Bugfix: Wrong material cost on Medium variant

**Root cause:** `calculate_product_cost()` checked cached `variant.estimated_filament_grams` first. When the Medium variant was calculated before its own model was uploaded, `_latest_model_analysis(variant=Medium)` found no variant-specific assets, fell back to product-level assets, and picked up the Large model's values (206.60g). These got cached onto the Medium variant. Every subsequent calculation saw non-zero cached values and **skipped the model analysis lookup entirely**, so Medium kept using Large's wrong values forever.

**Fix:** Model analysis data now always takes priority over cached values. PrusaSlicer output is the source of truth when available:
```python
model_data = _latest_model_analysis(product, variant)
if model_data:
    filament_grams = model_data["filament_grams"]
    print_minutes = model_data["print_minutes"]
else:
    # fall back to cached estimates
    filament_grams = variant.estimated_filament_grams
    print_minutes = variant.estimated_print_minutes
```
