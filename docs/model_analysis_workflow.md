# Model Analysis Workflow

From file upload to finished cost calculation in the product-studio-only catalog.

---

## 1. User drops a file in Product Studio

- `app/static/src/js/studio.js` handles click, drag-and-drop, filename preview, and
  a slicer-settings confirmation modal.
- The browser posts the model plus validated printer, material, slicing, retention,
  and GLB-conversion choices to `/products/studio/{product_id}/upload-model`.

## 2. Flask stores the model on the product record

**File:** `app/blueprints/products/studio_routes.py`

- Validates the upload with `ProductModelUploadForm`.
- Writes the file to product storage at `products/{product_id}/{filename}`.
- Stores the path directly on `Product.model_file_path`.
- Stores searchable settings in MariaDB and writes a versioned
  `*.metadata.json` sidecar beside the source asset.
- Resets analysis/conversion status fields on the same product row.
- Dispatches Celery task `analyze_product_model.delay(product_id)` when Celery is available.

## 3. Browser polls task status

- `GET /products/studio/task-status/{task_id}` is polled until success or failure.
- On success the page reloads and Product Studio shows the refreshed analysis/cost data.

## 4. Celery validates and slices the model

**File:** `app/tasks/model_analysis.py`

- Loads the uploaded model from storage.
- Runs `validate_model_file()` to extract:
  - volume
  - surface area
  - triangle count
- Runs `slice_with_prusaslicer()` to estimate:
  - filament grams
  - print minutes
- Writes parsed values back onto the `Product` row.
- Detects common embedded Prusa/Bambu/Orca settings in 3MF archives and applies
  them when requested.
- Uploads generated G-code when retention was requested.
- Triggers GLB conversion only when requested.
- Refreshes the JSON sidecar with geometry, results, warnings, and derived assets.

## 5. Cost engine uses product-level analysis

**File:** `app/services/cost_engine.py`

- Reads the latest parsed values directly from the product record.
- Resolves spool cost from current filament inventory.
- Calculates:
  - material cost
  - labor cost
  - machine cost
  - failure adjustment
  - total cost
  - suggested price
  - margin
- Stores a product-level `CostSnapshot`.

## 6. Product Studio shows the result

- Product Studio reads analysis, pricing, model preview, and images from the same `Product` record.
- There is no separate variant or model-asset layer in the active workflow anymore.

## 7. Product-scoped assets

- The existing Product Studio product selector is unchanged.
- `Assets` opens a modal backed by a live listing of the selected product's S3 prefix.
- Hover details come from the JSON sidecar; downloads use authenticated routes.
