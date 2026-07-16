# PMP Integration Implementation Plan

## Goal

Integrate the Pack My Plate (`pmp/`) bed-nesting engine into DFPos so an authorized operator can:

1. Select a product with an STL or 3MF model asset.
2. Choose a printer and packing parameters.
3. Generate and review an SVG bed preview.
4. Save a packed 3MF artifact without overwriting the source model.
5. Create a print job linked to the packed artifact and packing run.
6. Optionally upload, analyze, and post-process sliced G-code in a later phase.

The integration remains Flask-first, server-authoritative, feature-flagged, business-scoped, permission-protected, and audited.

## Requested Product Studio Workflow

The primary operator workflow is:

1. Open a product in Product Studio.
2. Click **Pack the Plate**.
3. DFPos selects the product's latest successfully uploaded source model whose verified type is STL or 3MF.
4. DFPos invokes PMP directly with that source file.
5. The operator configures/reviews the packing result and confirms generation.
6. PMP produces a packed 3MF.
7. DFPos saves the packed 3MF in the same product asset directory as the source file.
8. DFPos registers the generated file as a separate product model asset.
9. The file explorer refreshes and shows both the original source and the new packed-plate output.

“Latest uploaded model” must mean the newest source upload by database `created_at` and ID—not filesystem modification time, object-store listing order, `converted_model_path`, or the newest generated packed file. A packed output must never silently become the source for a later packing run unless the operator explicitly chooses it.

### Output filename

Use this default display/storage filename:

```text
<source-stem>__packed-plate__<YYYYMMDD-HHMMSSZ>.3mf
```

Example:

```text
rainbow-dragon__packed-plate__20260714-221530Z.3mf
```

Rules:

- Sanitize `<source-stem>` with the existing storage filename helper.
- Always use a UTC timestamp.
- Always use the `.3mf` extension, including when the source is STL.
- If the key already exists, append a short packing-run identifier before `.3mf`.
- Preserve the original uploaded/display filename in the asset record even if the physical storage key uses a UUID or sanitized name.
- Show a **Packed Plate** badge in the file explorer so identification does not depend only on the filename.

### Product model asset history

The present `Product.model_file_path` field holds only one current source and is not sufficient for a file explorer or upload history. Add a `ProductModelAsset` model (or extend an existing generalized asset model if one is introduced before implementation) with at least:

- `product_id` and `business_id`.
- `storage_reference` and `original_filename`.
- `asset_kind`: `source_model`, `converted_model`, `packed_plate`, or `gcode`.
- `file_format`: `stl`, `3mf`, or the relevant supported format.
- `source_asset_id` for generated/converted lineage.
- Optional `packing_run_id` for packed outputs.
- File size, SHA-256, upload/generation actor, and timestamps.
- Analysis/validation status and archival timestamp where appropriate.

`Product.model_file_path` may remain temporarily as the current-source compatibility pointer, but the asset table becomes the source of truth for history and file-explorer rendering. New uploads create `source_model` rows; packing creates `packed_plate` rows linked to both the selected source asset and packing run.

The file explorer should order assets newest first and show filename, type, source/generated badge, size, created time, creator, related packing run, and actions such as preview/download/archive. It must use authorized download routes rather than expose local paths or S3 references.

## Current Repository Findings

The implementation should build on what already exists:

- `pmp/packing.py`, `pmp/threemf.py`, and `pmp/gcode.py` contain the core PMP behavior.
- Product Studio already accepts `.stl` and `.3mf` files.
- `Product` already has `model_file_path`, `converted_model_path`, `parsed_volume_mm3`, and `parsed_triangle_count`.
- Product Studio currently presents the current model file but does not yet persist a browsable model-asset history; that foundation is part of this work.
- `app/tasks/model_analysis.py` already analyzes model assets and converts supported inputs.
- Product files already use the application's storage abstraction and per-product storage layout.
- The application already depends on `trimesh` and `numpy` for model analysis, but PMP still needs its own direct STL input path so packing does not require a prior conversion task.
- `Printer` does not yet store bed dimensions.
- `PrintJob` does not yet reference packed 3MF or G-code artifacts.
- `pmp/` is source code but is not currently an installable Python package with its own `pyproject.toml`.
- `pmp/threemf.py` expects `pmp/data/u1_project_settings.json`, while this checkout currently has `pmp/u1_project_settings.json`. This must be fixed before packaging.

## Architecture Decisions

### STL parser recommendation

PMP must accept STL as a first-class source format. Invoking PMP with an STL should run the same packing operation and produce the same preview, statistics, placements, and packed-3MF deliverable as invoking it with a 3MF.

Add a pure-standard-library STL reader inside PMP rather than requiring DFPos to convert the file first. The reader must return an indexed mesh—not only deduplicated footprint vertices—so the STL geometry can be written into the generated 3MF:

```python
@dataclass
class STLMesh:
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    source_format: Literal["binary_stl", "ascii_stl"]
```

Decision:

- PMP directly accepts `.stl` and `.3mf` inputs through one public packing entry point.
- Parse both binary and ASCII STL with a bounded, pure-stdlib reader.
- Detect binary STL primarily from its declared triangle count and expected byte length; do not assume a file beginning with `solid` is ASCII because valid binary files may use that header text.
- Deduplicate vertices while retaining triangle indices and reject invalid/non-finite coordinates, truncated records, empty meshes, and configured complexity/size-limit violations.
- Do not add `numpy-stl`. DFPos may continue using `trimesh` for its separate model-analysis workflow, but PMP packing must not depend on that preprocessing step.
- Cover binary, ASCII, malformed, truncated, oversized, non-finite, degenerate, and misleading `solid`-header files with fixtures.

The common pipeline begins after loading:

```text
STL  -> parse indexed mesh -----------+
                                      +-> footprint -> pack -> preview/stats
3MF  -> load mesh/build/resources ----+
```

Output differs only where the source formats require it:

- 3MF input uses surgical save so source resources and paint information are preserved.
- STL input creates a new standards-compliant 3MF containing the source mesh and one transformed build item per placement. STL has no paint metadata, so the generated project uses configured/default filament colors.

### Keep PMP as an internal package

Package `pmp/` as a normal Python package in this repository and import it directly. Do not use a machine-specific absolute `file://` dependency. If PMP later becomes independently versioned, move it to a workspace/path dependency with its own tests and release process.

### Reuse existing model ingestion

Product Studio remains responsible for secure model upload, storage, validation, metadata extraction, and conversion. Packing consumes the resolved local copy of a stored asset through the storage service. It must not assume that `model_file_path` is a local filesystem path.

### Persist packing runs and artifacts

Do not store transient preview state only in a session or overwrite `Product.converted_model_path`. Add a `PackingRun` record for reproducibility, status, parameters, results, warnings, source identity, output artifact, actor, business, and optional print job. This keeps multiple layouts and preserves the original model.

### Run expensive packing outside the request when necessary

Small jobs may complete synchronously. The service must support dispatch through the existing Celery infrastructure for large models or fill-bed operations. The UI polls or uses HTMX for status and renders success/failure states.

### Treat generated files as untrusted inputs and controlled outputs

Apply size limits, extension and magic-byte checks, ZIP safety checks for 3MF, bounded mesh complexity, bounded count/angles, time limits, safe storage keys, and authorized download routes. Never accept an arbitrary server path from browser or API input.

## Delivery Phases

### Phase 0 — PMP stabilization and contract tests

Scope:

- Make `pmp` importable under Python 3.14 using package-relative imports.
- Move/package `u1_project_settings.json` where `threemf.py` expects it, preferably through `importlib.resources`.
- Define a small public PMP API instead of importing private helpers such as `_fmt_bed`.
- Add PMP's indexed binary/ASCII STL reader and a minimal 3MF builder for STL-source output.
- Add one public source-loading/packing entry point that dispatches by verified file content and returns a format-neutral result.
- Add fixture-based tests for:
  - deterministic hull packing;
  - requested-count success and partial-fit warnings;
  - bed margin and reserved tower boundaries;
  - transform composition;
  - source 3MF paint preservation;
  - generated 3MF ZIP/XML validity;
  - equivalent placement behavior for geometrically identical STL and 3MF fixtures;
  - binary and ASCII versions of the same STL mesh;
  - malformed and oversized input rejection.
- Run PMP tests with the project environment before Flask integration.

Exit criteria:

- `uv run python -c "import pmp"` succeeds.
- PMP contract tests pass on Python 3.14.
- No production DFPos code imports PMP private names.

### Phase 1 — Persistence, printer capabilities, and migration

Add `ProductModelAsset` and backfill the current `Product.model_file_path`/`converted_model_path` references where present. New source uploads must write an asset row and update the compatibility pointer in the same successful workflow. Generated packed plates write an asset row but do not replace the current-source pointer.

Add printer fields:

- `bed_width_mm` and `bed_depth_mm` as `Numeric`, not `float`.
- Optional `build_height_mm` for validation and future slicer use.
- Optional `packing_profile_key`; do not hard-code every printer as Snapmaker U1.

Add `PackingRun` with at least:

- `id`, `business_id`, timestamps, and status (`queued`, `running`, `completed`, `failed`, `archived`).
- `product_id`, optional `printer_id`, optional `print_job_id`, and actor/user ID.
- Source asset ID, storage reference snapshot, source SHA-256, source type, and source size.
- Requested count, target dimension/scale policy, spacing, margin, angle step, mode, and tower setting.
- Effective bed dimensions and reserved area.
- Placement count, utilization values, method, warnings, and serialized placements.
- Preview SVG storage reference and packed 3MF storage reference.
- Output product-model-asset ID and collision-safe output filename.
- Error code/message suitable for operator display without leaking internals.

Update:

- Printer form and API schema.
- Print job model with optional `packing_run_id`, `packed_model_path`, and later `gcode_path`/`processed_gcode_path`.
- Demo seed values for the existing Bambu fleet (256 × 256 mm). Add Snapmaker U1 only if it is actually owned or clearly mark it as demo; do not silently add it to the real fleet.
- Module registry with a `packing` module depending on `products`, `printers`, and `print_jobs`.

Exit criteria:

- Migration upgrades and downgrades cleanly.
- Existing printer, product, and print-job tests continue to pass.
- Packing data is business-scoped and indexed on common lookup/status fields.
- Source selection deterministically returns the newest valid `source_model` asset and excludes generated outputs.
- Existing product model references are visible in the new file explorer after migration/backfill.

### Phase 2 — DFPos packing service

Create `app/services/packing.py` as the sole orchestration boundary.

Responsibilities:

1. Authorize and resolve the business-scoped product and printer.
2. Resolve/download the product asset through the storage abstraction.
3. Verify file type by content, not extension alone.
4. Pass the verified source to PMP's common entry point:
   - 3MF uses PMP's loader and preserves source resources/paint where supported.
   - STL uses PMP's indexed pure-stdlib reader directly; it does not require prior DFPos conversion or model-analysis completion.
5. Validate bounds for bed size, count, spacing, margin, angle step, mode, source size, vertex/triangle count, and execution time.
6. Call `pmp.packing.pack()` and normalize its result into a stable DFPos result object.
7. Generate a sanitized SVG preview. Do not inject untrusted model text into SVG.
8. Build the output:
   - source 3MF: surgical save with rewritten build items;
   - source STL: create a standards-compliant minimal 3MF with mesh and build items.
9. Validate the generated 3MF by reopening it before storage.
10. Store immutable artifacts under a packing-run-specific key.
11. Update the `PackingRun` atomically and dispatch audit events.

Required audit actions:

- `packing_run.created`
- `packing_run.completed`
- `packing_run.failed`
- `packing_artifact.downloaded`
- `print_job.created_from_packing`
- G-code actions added in Phase 6

Critical service tests:

- STL and 3MF happy paths.
- Painted 3MF preservation.
- Object transforms and multiple source build items.
- Remote/storage-backed source assets.
- Invalid ZIP/XML/STL and ZIP-bomb defenses.
- Count or geometry that cannot fit.
- Disabled module and cross-business denial.
- Storage, task, and audit failure behavior.
- Idempotent retry without duplicate artifacts or jobs.

Exit criteria:

- A service call creates a reproducible `PackingRun`, preview, and valid packed 3MF.
- Source assets remain unchanged.
- Failures leave a clear terminal state and no misleading completed artifact.

### Phase 3 — Admin workflow

Add a `packing` blueprint under `/admin/packing` with thin routes and WTForms validation.

Pages:

- Packing-run list with status, product, printer, operator, created date, and filters.
- New run: product, source asset, printer, count/fill-bed, spacing, margin, rotation step, mode, and tower reserve.
- Run detail/preview: SVG, placements, utilization, warnings, source/output metadata, retry, archive, download, and create-print-job actions.
- HTMX status partial for queued/running work.

Product Studio integration:

- Add **Pack the Plate** beside the Model File/File Explorer controls.
- Disable it with a clear explanation when no valid STL/3MF source upload exists.
- Resolve and display the selected latest source before starting; allow explicit source selection from history as a secondary action.
- After successful generation, refresh the file-explorer partial so the new `packed_plate` asset appears without a full-page reload.
- Keep the original source marked as the current source; do not replace `Product.model_file_path` with the packed output.

UX requirements:

- Use existing design tokens and admin components from `DESIGN.md`.
- Explain `count` versus fill-bed behavior and target scale clearly.
- Default from the selected printer but allow bed overrides only to authorized roles and within configured limits.
- Include loading, empty, partial-fit, validation, task-failure, download-failure, and success states.
- Require confirmation before retry/archive or replacing a print job's artifact.
- Hide unavailable actions and enforce the same rules server-side.

Exit criteria:

- An admin can complete the full product-to-packed-file workflow on mobile and desktop.
- Staff permissions, CSRF, feature flags, business scope, and secure downloads are tested.

### Phase 4 — REST API

Add API resources using the application's existing Flask-Smorest patterns:

- `POST /api/v1/packing-runs`
- `GET /api/v1/packing-runs`
- `GET /api/v1/packing-runs/<id>`
- `POST /api/v1/packing-runs/<id>/retry`
- `POST /api/v1/packing-runs/<id>/print-jobs`
- `GET /api/v1/packing-runs/<id>/preview`
- `GET /api/v1/packing-runs/<id>/artifact`

Avoid a single request that performs packing and job creation without a persisted intermediate result. The resource-oriented flow provides status, retries, idempotency, and auditability.

API requirements:

- Token authentication and packing/print-job scopes.
- Feature-flag and permission enforcement.
- Business scoping.
- Marshmallow request/response schemas.
- Consistent errors and HTTP status codes.
- Pagination/filtering/sorting for the collection.
- Idempotency key support for creation endpoints.
- OpenAPI documentation without exposing server storage paths.

Exit criteria:

- API behavior matches the admin service path and passes auth, scope, flag, validation, and idempotency tests.

### Phase 5 — Print-job creation and production linkage

Create print jobs through the existing print-job service, not directly in the route.

The operation must:

- Require a completed packing run and existing packed artifact.
- Link business, product, printer, packing run, and artifact.
- Set quantity from actual placements, not merely requested count.
- Carry packing warnings into operator-visible notes without losing structured data.
- Prevent accidental duplicate jobs through an idempotency key or explicit confirmation.
- Dispatch the required audit event.

Exit criteria:

- A packed run produces one correctly linked queued print job.
- Partial-fit runs use actual placement quantity.
- Retry and duplicate-submit tests do not create duplicate jobs.

### Phase 6 — G-code workflow (separate release)

Do not block initial packing delivery on G-code processing. After packed 3MF and print-job flows are stable:

- Add secure G-code upload to a specific print job.
- Store original and processed G-code separately and immutably.
- Add size limits and validate that content resembles supported G-code.
- Wrap `pmp.gcode` behind `app/services/gcode_processing.py`.
- Provide analyze, merge-plan preview, pause-plan preview, and explicit process actions.
- Keep every operation reproducible by storing selected options and analysis results.
- Audit upload, analysis, processing, replacement, download, and failure events.
- Test representative Bambu/Orca output and reject unsupported dialects safely.

Exit criteria:

- Operators can inspect proposed modifications before generating processed G-code.
- The original upload is never overwritten.
- Golden-file tests prove only intended commands change.

### Phase 7 — Operational hardening and documentation

- Add cleanup/retention rules for failed, superseded, preview, and generated artifacts.
- Add metrics for duration, queue latency, failures by reason, model complexity, and utilization.
- Add structured logs with request, task, packing-run, business, and actor IDs.
- Document worker requirements, storage capacity, timeouts, and recovery procedures.
- Add end-to-end coverage for upload → pack → preview → artifact → print job.
- Run Ruff, focused tests, the full Pytest suite, migration checks, and Docker smoke tests.
- Update `ARCHITECTURE.md`, API docs, README/operator docs, and `TODO.md` after each delivered phase.

## Suggested File Changes

New files will likely include:

- `app/models/packing.py`
- `app/models/product_model_asset.py` (unless kept with catalog models)
- `app/forms/packing.py`
- `app/schemas/packing.py`
- `app/services/packing.py`
- `app/tasks/packing.py`
- `app/blueprints/packing/__init__.py`
- `app/blueprints/packing/routes.py`
- `app/templates/packing/index.html`
- `app/templates/packing/configure.html`
- `app/templates/packing/detail.html`
- `app/templates/packing/_status.html`
- `app/templates/products/_model_file_explorer.html`
- `tests/test_pmp_contract.py`
- `tests/test_packing_service.py`
- `tests/test_packing_routes.py`
- `tests/test_packing_api.py`
- one Alembic migration for Phase 1

Expected edits include:

- `pmp/__init__.py`, `pmp/threemf.py`, and PMP package data layout
- `app/models/fleet.py`
- `app/models/print_job.py`
- `app/models/__init__.py`
- `app/forms/fleet.py`
- `app/schemas/fleet.py`
- `app/module_registry.py`
- `app/__init__.py`
- `app/blueprints/api/routes.py` or a split packing API module following current conventions
- `app/cli.py`
- `ARCHITECTURE.md`
- `TODO.md`
- operator/API documentation

## Recommended Work Slices

Implement and review one slice at a time:

1. PMP stabilization and contract tests.
2. Product model asset history, PackingRun/printer schema, and migration.
3. Product Studio file explorer plus synchronous service path for one STL fixture and one 3MF fixture.
4. Storage-backed artifacts, async task path, retries, and audit behavior.
5. Admin workflow.
6. REST API.
7. Print-job linkage.
8. G-code workflow.
9. Operational hardening and full verification.

The first useful release is complete after slices 1–7. G-code processing is intentionally a follow-up release because it has different safety, compatibility, storage, and verification risks.

## Definition of Done

The PMP integration is complete when:

- STL and 3MF assets can be packed from local or configured object storage.
- Source files are preserved and generated files are validated and immutable.
- Packing runs are reproducible, business-scoped, permission-protected, feature-flagged, and audited.
- Admin and API workflows share the same service logic.
- A completed run can create a correctly linked print job using actual placement count.
- Disabled-module, malformed-file, oversized-file, timeout, storage-failure, audit-failure, and duplicate-submit paths are tested.
- Migrations, Python 3.14 dependency resolution, formatting, tests, and Docker smoke checks pass.
- Architecture, API, operator, and task-tracking documentation is current.
