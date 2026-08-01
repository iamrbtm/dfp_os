# Bambu-Primary Product Slicing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution, or superpowers:subagent-driven-development only when the user explicitly authorizes subagents.

**Goal:** Make Bambu Studio 2.7.1.62 the primary slicer for the staged Add Product/model-analysis pipeline, retain PrusaSlicer as an automatic estimate-only fallback, and persist the correct native artifact and engine metadata without changing or deleting database data.

**Architecture:** Keep one FastAPI slicer microservice and split its current Prusa-only implementation into engine adapters behind a Bambu-first orchestrator. Add a binary artifact response endpoint while retaining the legacy JSON endpoint, then stream that artifact through the Flask client into the existing `ProductModelAsset`, `ProductAnalysisRun`, product summary, and cost snapshot flow. Reuse existing JSON columns and the existing `AssetKind.GCODE`; no migration is required.

**Tech Stack:** Python 3.14, FastAPI/Pydantic, Flask/Celery/SQLAlchemy, httpx streaming, Bambu Studio AppImage 2.7.1.62, Debian PrusaSlicer, Docker Compose, uv, Pytest, Ruff.

## Global constraints

- Never delete Docker volumes, database volumes, or project containers.
- Never run `docker system prune --volumes` or any equivalent volume cleanup.
- Keep OrcaSlicer out of the runtime, configuration, UI, and dependency graph.
- Preserve the staged workflow: save product first, then upload and analyze its model.
- Support only the existing Bambu A1, X1 Carbon, and P1P profiles with a 0.4 mm nozzle in this phase.
- Use Bambu Studio first. Use PrusaSlicer only for explicitly fallback-eligible engine failures.
- Mark every Prusa result `estimate_only=true` and `direct_print_eligible=false`.
- Preserve Bambu `.gcode.3mf` output and Prusa `.gcode` output; never convert one into the other.
- Invoke slicers with argument arrays and `shell=False`; do not accept executable paths or profile paths from requests.
- Keep uploaded names reduced to safe basenames and clean temporary workspaces on every path.
- Follow strict TDD: add one focused failing test, observe the intended failure, implement the minimum behavior, then rerun the focused test.
- Commit only the files named by each task and preserve unrelated working-tree changes.

## Fixed runtime inputs

- Bambu Studio version: `2.7.1.62`
- Git tag: `v02.07.01.62`
- AppImage URL: `https://github.com/bambulab/BambuStudio/releases/download/v02.07.01.62/BambuStudio_ubuntu22.04-v02.07.01.62-20260616195227.AppImage`
- AppImage SHA-256: `2749917af560f3b9a2681429da9c43d00c65d096e1a1c479cc49466634174549`
- Installed Bambu command: `/opt/bambu-studio/AppRun`
- Installed Bambu profile root: `/opt/bambu-studio/resources/profiles/BBL`
- Engine order: `bambu,prusa`
- Binary metadata response header: `X-DFPOS-Slicer-Metadata`
- Maximum encoded metadata header size: `6144` bytes
- Maximum slicer-service model upload size: `268435456` bytes (256 MiB)

## Result contract

The service-level result shared by both adapters must expose these fields:

```python
@dataclass
class EngineArtifact:
    engine_key: str
    engine_name: str
    engine_version: str
    artifact_path: Path
    artifact_filename: str
    artifact_media_type: str
    artifact_size: int
    artifact_sha256: str
    filament_grams: Decimal
    print_minutes: Decimal
    layer_count: int | None
    profile_ids: dict[str, str]
    direct_print_eligible: bool
    estimate_only: bool
    diagnostics: dict[str, object] = field(default_factory=dict)

@dataclass
class EngineFailure:
    engine_key: str
    code: str
    message: str
    fallback_eligible: bool
    diagnostics: dict[str, object] = field(default_factory=dict)
```

The compact public metadata stored in the response header and analysis run must contain:

```text
success, engine_key, engine_name, engine_version,
fallback_used, primary_failure,
filament_grams, print_minutes, layer_count,
profile_ids,
artifact_filename, artifact_media_type, artifact_size, artifact_sha256,
direct_print_eligible, estimate_only
```

Do not put raw stdout/stderr or internal temporary paths into the header. Log those server-side and keep the public primary failure to a stable code plus a bounded administrator message.

---

### Task 1: Mark the feature active and establish engine-domain tests

**Files:**

- Modify: `TODO.md`
- Create: `services/slicer/app/services/engines/__init__.py`
- Create: `services/slicer/app/services/engines/base.py`
- Create: `services/slicer/app/tests/test_engine_contract.py`

**Step 1: Mark the current work**

Add an `in-progress` Current Focus entry stating that the Product Studio model pipeline is moving to Bambu-primary/Prusa-fallback slicing with native artifact storage.

**Step 2: Write failing contract tests**

Test that:

- `SliceOptions.from_request(model_filename, ...)` normalizes `bambu_a1.ini` to `bambu_a1`.
- `SliceOptions` accepts only `bambu_a1`, `bambu_p1p`, and `bambu_x1c`.
- It rejects any nozzle other than `Decimal("0.4")` with a terminal `RequestValidationError`.
- It accepts only `PLA`, `PETG`, `ABS`, `ASA`, and `TPU`.
- It rejects unsupported suffixes before an engine is called.
- `EngineFailure` distinguishes fallback-eligible engine failure from terminal request failure.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_engine_contract.py
```

Expected: FAIL because the engine package and types do not exist.

**Step 3: Implement the minimum domain layer**

In `base.py`, add:

- `SUPPORTED_PRINTERS`, `SUPPORTED_MATERIALS`, `SUPPORTED_MODEL_SUFFIXES`.
- Frozen `SliceOptions` with `from_request(profile_name, slicer_options, preserve_orientation)`.
- `RequestValidationError(code, message)`.
- `EngineProbe`, `EngineArtifact`, and `EngineFailure` dataclasses.
- `SlicerEngine` protocol with `probe()` and `slice(model_path, workspace, options)`.
- `sha256_file(path)` and `safe_artifact_filename(value)` helpers.

Do not put Bambu- or Prusa-specific CLI flags in this module.

**Step 4: Run focused tests**

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_engine_contract.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add TODO.md services/slicer/app/services/engines services/slicer/app/tests/test_engine_contract.py
git commit -m "feat(slicer): add engine-neutral slice contract"
```

---

### Task 2: Extract the existing Prusa implementation into the secondary adapter

**Files:**

- Create: `services/slicer/app/services/engines/stats.py`
- Create: `services/slicer/app/services/engines/prusa.py`
- Modify: `services/slicer/app/services/slicer.py`
- Create: `services/slicer/app/tests/test_prusa_engine.py`
- Modify: `services/slicer/app/tests/test_slicer_options.py`

**Step 1: Write failing Prusa adapter tests**

Use a fake `subprocess.run` and assert that the adapter:

- Probes `prusa-slicer --version` and captures a stable version string.
- Maps the three allowed printer identifiers to the existing `.ini` profiles.
- Preserves the existing fill-density normalization (`0.2`, `20`, and `20%` become `20%`).
- Passes layer height, walls, top/bottom layers, infill, support, brim, nozzle, density, and material flags.
- Returns a `.gcode` `EngineArtifact` with parsed time/filament/layer stats.
- Sets `estimate_only=True` and `direct_print_eligible=False`.
- Classifies missing executable, timeout, nonzero exit, missing output, and missing required estimates as fallback-eligible engine failures.
- Never includes more than 512 characters of stderr in its returned diagnostic.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_prusa_engine.py
```

Expected: FAIL because `PrusaEngine` does not exist.

**Step 2: Move shared G-code parsing**

Move `_parse_time_string`, `_parse_gcode_stats`, density fallback, and fill-density normalization into `engines/stats.py`. Keep their observable output unchanged so the current parser tests remain valid.

**Step 3: Implement `PrusaEngine`**

- Constructor inputs: executable path and the existing profile directory.
- Build commands as lists; never interpolate a shell string.
- Write output into the request workspace, not beside the uploaded source.
- Return `EngineArtifact` on success and `EngineFailure` on failure.
- Keep the legacy `slice_model(...)` function as a thin compatibility wrapper around `PrusaEngine` that still returns `SlicerStats` with optional G-code text for `/api/v1/slice`.

**Step 4: Run focused and regression tests**

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_prusa_engine.py app/tests/test_slicer_options.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add services/slicer/app/services services/slicer/app/tests/test_prusa_engine.py services/slicer/app/tests/test_slicer_options.py
git commit -m "refactor(slicer): isolate Prusa fallback adapter"
```

---

### Task 3: Resolve full Bambu profiles from the pinned AppImage resources

**Files:**

- Create: `services/slicer/app/services/engines/bambu_profiles.py`
- Create: `services/slicer/app/tests/test_bambu_profiles.py`

**Step 1: Write failing resolver tests**

Build a minimal temporary profile tree in the test and verify:

- The index uses JSON `name` values, not request paths.
- `inherits` is recursively merged from oldest ancestor to selected profile.
- `include` fragments are merged in listed order before the selected profile overrides them.
- A cycle or missing parent raises `BambuProfileError` with a stable code.
- Request values cannot escape the allowlisted profile matrix.
- Flattened JSON is written into the request workspace.
- The matrix resolves these exact official names:

| Printer | Machine | Process | Filament names |
|---|---|---|---|
| `bambu_a1` | `Bambu Lab A1 0.4 nozzle` | `0.20mm Standard @BBL A1` | `Generic {MATERIAL} @BBL A1` |
| `bambu_p1p` | `Bambu Lab P1P 0.4 nozzle` | `0.20mm Standard @BBL P1P` | `Generic {MATERIAL} @BBL P1P` |
| `bambu_x1c` | `Bambu Lab X1 Carbon 0.4 nozzle` | `0.20mm Standard @BBL X1C` | `Generic {MATERIAL}` |

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_bambu_profiles.py
```

Expected: FAIL because the resolver does not exist.

**Step 2: Implement the cached resolver**

Add `BambuProfileResolver(profile_root)` with:

- A sorted recursive scan of `*.json` under the configured BBL root.
- A one-to-one name index; reject duplicates instead of choosing silently.
- Recursive flattening with cycle detection.
- `resolve(printer_key, material, workspace) -> ResolvedBambuProfiles`.
- Output files `machine.json`, `process.json`, and `filament.json` in the workspace.
- A public `profile_ids` dict containing vendor profile names, not filesystem paths.

Cache the immutable index and flattened objects for the process lifetime, but write fresh per-request files so concurrent slices cannot overwrite one another.

**Step 3: Run focused tests**

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_bambu_profiles.py
```

Expected: PASS.

**Step 4: Commit**

```bash
git add services/slicer/app/services/engines/bambu_profiles.py services/slicer/app/tests/test_bambu_profiles.py
git commit -m "feat(slicer): resolve pinned Bambu profiles"
```

---

### Task 4: Add the Bambu Studio primary adapter

**Files:**

- Create: `services/slicer/app/services/engines/bambu.py`
- Create: `services/slicer/app/tests/test_bambu_engine.py`
- Create: `services/slicer/app/tests/fixtures/cube.stl`

**Step 1: Write failing Bambu command and artifact tests**

Use a fake executable runner and synthetic `.gcode.3mf` ZIP containing `Metadata/plate_1.gcode`. Verify:

- Probe calls `AppRun --help` and parses `BambuStudio-02.07.01.62` as `2.7.1.62`.
- The command includes `--load-settings machine.json;process.json`, `--load-filaments filament.json`, `--arrange 1`, `--slice 0`, and `--export-3mf <safe>.gcode.3mf`.
- `--orient` is included only when uploaded orientation is not preserved.
- Engine-neutral options map to Bambu keys:
  - `layer_height` -> `--layer-height=<value>`
  - `perimeters` -> `--wall-loops=<value>`
  - top/bottom layers -> `--top-shell-layers` / `--bottom-shell-layers`
  - infill -> `--sparse-infill-density=<value>%` and `--sparse-infill-pattern=<value>`
  - no supports -> `--enable-support=0`
  - supports everywhere -> `--enable-support=1` and `--support-on-build-plate-only=0`
  - build-plate-only supports -> `--enable-support=1` and `--support-on-build-plate-only=1`
  - brim -> `--brim-width=<value>`
- Argument values remain individual list entries and no shell is used.
- Success requires a valid ZIP, at least one `Metadata/plate_*.gcode`, filament grams, and print minutes.
- The adapter hashes the final file and returns media type `application/vnd.bambulab.gcode-3mf`.
- Bambu success sets `direct_print_eligible=True` and `estimate_only=False`.
- Missing executable, timeout, crash/nonzero exit, malformed ZIP, missing G-code, or missing estimates returns a fallback-eligible failure.
- Unsupported printer/nozzle/material and unsafe extension remain terminal request failures and are not reclassified.
- `multicolor=true` is terminal for STL/OBJ in this phase; only a 3MF with `use_embedded_settings=true` may proceed without inventing color assignments.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_bambu_engine.py
```

Expected: FAIL because `BambuEngine` does not exist.

**Step 2: Implement `BambuEngine`**

- Constructor inputs: executable path, `BambuProfileResolver`, timeout (default 600 seconds).
- Call the resolver, construct the documented CLI argument list, and capture stdout/stderr.
- Use `zipfile` to validate output and read the plate G-code member for estimates.
- Bound returned diagnostics and never expose the workspace path.
- Do not add printer discovery, cloud login, MQTT, FTP, or network code.

**Step 3: Run focused tests**

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_bambu_engine.py
```

Expected: PASS.

**Step 4: Commit**

```bash
git add services/slicer/app/services/engines/bambu.py services/slicer/app/tests/test_bambu_engine.py services/slicer/app/tests/fixtures/cube.stl
git commit -m "feat(slicer): add Bambu Studio primary adapter"
```

---

### Task 5: Implement Bambu-first orchestration and strict fallback policy

**Files:**

- Create: `services/slicer/app/services/engines/orchestrator.py`
- Create: `services/slicer/app/tests/test_slicer_orchestrator.py`

**Step 1: Write failing orchestration tests**

With fake engines, assert:

- Bambu success returns immediately and never calls Prusa.
- Bambu unavailable, timeout, crash, nonzero exit, invalid/missing artifact, or missing estimates calls Prusa once.
- A Prusa fallback result carries `fallback_used=True` and the bounded Bambu failure code/message.
- Unsupported printer, nozzle, material, profile, suffix, or malformed request never calls Prusa. Authentication is rejected at the API boundary in Task 6 before orchestration.
- Bambu failure plus Prusa failure returns both stable engine failure codes.
- A fallback artifact is always estimate-only and never direct-print eligible.
- Default order is exactly `bambu,prusa`; unknown configured engine keys fail service startup/config validation.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_slicer_orchestrator.py
```

Expected: FAIL because the orchestrator does not exist.

**Step 2: Implement orchestration**

Add `SlicerOrchestrator.slice(model_path, workspace, options)` and an `OrchestratedResult` that contains either the selected artifact or terminal failure details. The orchestrator owns fallback policy; adapters must not call each other.

**Step 3: Run focused tests**

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_slicer_orchestrator.py
```

Expected: PASS.

**Step 4: Commit**

```bash
git add services/slicer/app/services/engines/orchestrator.py services/slicer/app/tests/test_slicer_orchestrator.py
git commit -m "feat(slicer): orchestrate Bambu with Prusa fallback"
```

---

### Task 6: Expose the binary artifact endpoint, auth, and engine-aware health

**Files:**

- Create: `services/slicer/app/api/auth.py`
- Modify: `services/slicer/app/api/routes/slice.py`
- Modify: `services/slicer/app/api/routes/health.py`
- Modify: `services/slicer/app/schemas/health.py`
- Modify: `services/slicer/app/schemas/slice.py`
- Modify: `services/slicer/app/config.py`
- Create: `services/slicer/app/tests/test_slice_artifact_api.py`
- Create: `services/slicer/app/tests/test_health.py`

**Step 1: Write failing endpoint/auth tests**

Using FastAPI `TestClient` and a fake orchestrator, assert:

- Missing or incorrect bearer token returns 401 before reading/calling the slicer.
- `POST /api/v1/slice-artifact` accepts the existing multipart model upload plus engine-neutral form settings.
- Success streams raw artifact bytes with the artifact media type, safe `Content-Disposition`, and base64url JSON metadata header.
- Decoded metadata matches the Result Contract and the encoded header is under 6144 bytes.
- Validation failures return structured JSON with HTTP 422 and never fall back.
- The endpoint copies the upload in bounded chunks, returns HTTP 413 after 256 MiB, and removes the partial workspace without calling an engine.
- No available engine returns structured JSON with HTTP 503.
- The legacy `POST /api/v1/slice` still returns its current JSON shape and now also requires bearer auth.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_slice_artifact_api.py
```

Expected: FAIL because the route and auth dependency do not exist.

**Step 2: Implement auth and streamed response**

- Compare bearer tokens with `secrets.compare_digest`.
- Use a request-owned temporary directory.
- Copy `UploadFile` to disk in 1 MiB chunks while enforcing `max_model_bytes`; do not call `await model_file.read()` without a size.
- Return `FileResponse` with a Starlette `BackgroundTask` that removes that exact directory after the response completes.
- Encode only the compact metadata allowlist; if it exceeds the configured cap, fail before returning the artifact.
- Preserve safe filename normalization for Windows and POSIX upload names.

**Step 3: Write failing health tests**

Assert these readiness modes:

- Bambu available -> HTTP 200 body mode `primary`.
- Bambu unavailable and Prusa available -> HTTP 200 body mode `fallback_only`.
- Neither available -> HTTP 503 body mode `unhealthy`.
- Each engine reports `available`, version, and a stable error code when unavailable.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_health.py
```

Expected: FAIL on the current Prusa-only response.

**Step 4: Implement engine-aware configuration and health**

Add settings:

```text
bambu_studio_path=/opt/bambu-studio/AppRun
bambu_profile_root=/opt/bambu-studio/resources/profiles/BBL
engine_order=bambu,prusa
slice_timeout_seconds=600
metadata_header_max_bytes=6144
max_model_bytes=268435456
```

Build the adapters/orchestrator from settings in one factory function so routes and health share the same configuration.

**Step 5: Run service suite**

```bash
cd services/slicer
uv run --extra dev pytest -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add services/slicer/app/api services/slicer/app/config.py services/slicer/app/schemas services/slicer/app/tests
git commit -m "feat(slicer): stream authenticated slice artifacts"
```

---

### Task 7: Stream the binary artifact through the Flask slicer client

**Files:**

- Modify: `app/services/slicer_client.py`
- Modify: `app/services/model_analysis.py`
- Modify: `tests/test_model_analysis_slicer_client.py`

**Step 1: Write failing client tests**

Use `httpx.MockTransport` or a fake client response to verify:

- `SlicerClient.slice_artifact(...)` sends the bearer token and existing multipart settings to `/api/v1/slice-artifact`.
- It decodes padded and unpadded base64url metadata safely.
- It streams chunks to a destination under the supplied workspace rather than loading the artifact into JSON.
- It verifies response size and SHA-256 against metadata and deletes a corrupt partial file.
- It returns a bounded service error for JSON 4xx/5xx responses.
- `slice_with_slicer(...)` returns a `SlicerResult` containing artifact path/name/media type/hash/size plus engine metadata.
- Keep `slice_with_prusaslicer(...)` as a temporary compatibility alias that delegates to `slice_with_slicer`, so unrelated callers do not break during this phase.

Run:

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_model_analysis_slicer_client.py
```

Expected: FAIL because only the JSON client exists.

**Step 2: Implement streaming**

Extend `SlicerResult` with:

```text
artifact_path, artifact_filename, artifact_media_type,
artifact_size, artifact_sha256,
engine_key, engine_name, engine_version,
fallback_used, direct_print_eligible, estimate_only
```

Store the remaining compact metadata in `stats`. Never decode Bambu output as text.

**Step 3: Run focused tests**

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_model_analysis_slicer_client.py tests/test_model_analysis_parser.py
```

Expected: PASS.

**Step 4: Commit**

```bash
git add app/services/slicer_client.py app/services/model_analysis.py tests/test_model_analysis_slicer_client.py
git commit -m "feat(products): stream slicer artifacts to analysis"
```

---

### Task 8: Persist native artifacts and engine metadata in the Add Product pipeline

**Files:**

- Modify: `app/tasks/model_analysis.py`
- Modify: `app/services/product_analysis.py`
- Modify: `app/services/storage.py`
- Modify: `tests/test_product_asset_storage.py`
- Modify: `tests/test_phase0_data_model.py`
- Create: `tests/test_model_analysis_artifact_persistence.py`

**Step 1: Write failing storage and model tests**

Assert:

- The preferred Bambu filename ends in `.gcode.3mf`; Prusa ends in `.gcode`.
- Storage keys preserve the double extension safely.
- Creating a current `AssetKind.GCODE` marks the previous current G-code artifact stale, while source-model behavior remains unchanged.
- A completed run points `gcode_asset_id` at the new `ProductModelAsset`.
- The asset records the response media type, byte size, and SHA-256.

Run:

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_product_asset_storage.py tests/test_phase0_data_model.py tests/test_model_analysis_artifact_persistence.py
```

Expected: FAIL because task output is hardcoded to `quote.gcode`, text/plain, and no generated asset row is created.

**Step 2: Refactor the analysis task**

- Replace the Prusa-named call with `slice_with_slicer` and a workspace destination.
- Remove the old centered/uncentered Prusa retry; engine orientation/arrangement belongs inside adapters.
- On success, stream/copy the artifact with `upload_file_to_storage(...)` using the returned safe filename and media type; do not load it into a JSON response or a second in-memory byte buffer.
- Create a current `ProductModelAsset(asset_kind=AssetKind.GCODE)` and set `run.gcode_asset_id`.
- Continue setting `product.gcode_path` for backward compatibility.
- Populate `run.slicer_stats_json` with the full compact result contract, copy count/cost data, and `primary_failure` when fallback was used.
- Keep existing product parsed grams/minutes, cost calculation, immutable snapshot, supersession guard, GLB conversion, and audit dispatch.
- Include `engine_key`, `fallback_used`, `estimate_only`, and artifact SHA in `model_analysis.completed` audit metadata.
- If `retain_gcode` is false, do not upload/create the artifact, but still retain engine/stat metadata and costs.

**Step 3: Run focused pipeline tests**

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_product_asset_storage.py tests/test_phase0_data_model.py tests/test_model_analysis_artifact_persistence.py tests/test_phase2_analysis.py
```

Expected: PASS.

**Step 4: Commit**

```bash
git add app/tasks/model_analysis.py app/services/product_analysis.py app/services/storage.py tests/test_product_asset_storage.py tests/test_phase0_data_model.py tests/test_model_analysis_artifact_persistence.py
git commit -m "feat(products): persist native slicer artifacts"
```

---

### Task 9: Enforce the 0.4 mm product profile matrix and display engine results

**Files:**

- Modify: `app/forms/studio.py`
- Modify: `app/blueprints/products/studio_routes.py`
- Modify: `app/templates/products/studio.html`
- Modify: `tests/test_phase4_ux.py`
- Create or modify: `tests/test_product_studio_model_upload.py`

**Step 1: Write failing form/route tests**

Assert:

- New submissions store bare printer keys (`bambu_a1`, `bambu_x1c`, `bambu_p1p`), while old `.ini` values normalize on read.
- Nozzle is a fixed select/read-only 0.4 mm value and server validation rejects tampered non-0.4 input.
- The route never accepts engine names, executable paths, or profile filesystem paths from form data; service configuration owns the fixed `bambu,prusa` order.
- Invalid printer/material/nozzle returns the current friendly upload validation response and does not queue Celery.

Run:

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_product_studio_model_upload.py
```

Expected: FAIL because nozzle accepts 0.1–2.0 and printer values use `.ini`.

**Step 2: Implement form and route normalization**

- Change printer choices to bare stable identifiers.
- Change nozzle to a single-choice `SelectField` with decimal/string `0.4`, plus explicit server validation.
- Continue collecting the current material, layer, walls, infill, supports, brim, copies, scale, orientation, embedded settings, conversion, and retention choices.
- Preserve old saved `.ini` values by normalizing with `Path(value).stem` when prepopulating/processing.

**Step 3: Write failing presentation tests**

Create a current analysis run with Bambu metadata and another with Prusa fallback metadata. Assert the rendered Product Studio shows:

- Engine display name and version.
- Printer/process/filament profile names.
- Artifact type and direct-print eligibility.
- A semantic warning with text (not color alone) when Prusa fallback was used.
- The bounded Bambu primary failure reason for administrators.

Run:

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_phase4_ux.py -k slicer
```

Expected: FAIL because the current panel shows only aggregate analysis status/time/cost.

**Step 4: Render current run metadata**

Pass `get_current_run(product.id)` from `_render_studio`. Add one compact engine status card under the existing cost cards using existing semantic design tokens. Do not hardcode colors and do not create a new page or SPA.

**Step 5: Run focused UX tests**

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_product_studio_model_upload.py tests/test_phase4_ux.py
```

Expected: PASS.

**Step 6: Commit**

```bash
git add app/forms/studio.py app/blueprints/products/studio_routes.py app/templates/products/studio.html tests/test_product_studio_model_upload.py tests/test_phase4_ux.py
git commit -m "feat(products): show Bambu analysis and Prusa fallback"
```

---

### Task 10: Pin Bambu Studio in the prebuilt local slicer base image

**Files:**

- Modify: `services/slicer/Dockerfile.base`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `services/slicer/.dockerignore` only if the current context lacks one and build-context exclusions are needed
- Create: `services/slicer/app/tests/test_runtime_config.py`

**Step 1: Write failing configuration tests**

Assert defaults for Bambu executable/profile root, Prusa executable, engine order, timeout, and header cap.

Run:

```bash
cd services/slicer
uv run --extra dev pytest -q app/tests/test_runtime_config.py
```

Expected: FAIL because Bambu settings are absent.

**Step 2: Update `Dockerfile.base`**

Keep `FROM python:3.14-slim`, Python env vars, `appuser`, `/app`, and `/opt/venv` ownership. In the existing apt layer install with `--no-install-recommends`:

```text
prusa-slicer
curl
libwebkit2gtk-4.1-0
libgl1
ca-certificates
```

Then:

- Download the fixed official AppImage URL to `/tmp`.
- Verify the exact SHA-256 with `sha256sum -c` before execution.
- Extract it with `--appimage-extract` into `/opt/bambu-studio`.
- Remove the downloaded AppImage and apt lists.
- Ensure all runtime files are world-readable/executable and usable by `appuser`.
- Run `/opt/bambu-studio/AppRun --help` as a build-time smoke check.

Do not move any slicer installation back into `services/slicer/Dockerfile`; normal app/code rebuilds must continue to start from `dfpos-slicer-base:${DFPOS_IMAGE_TAG:-local}`.

**Step 3: Wire Compose/env configuration**

Add these slicer environment values:

```env
SLICER_BAMBU_STUDIO_PATH=/opt/bambu-studio/AppRun
SLICER_BAMBU_PROFILE_ROOT=/opt/bambu-studio/resources/profiles/BBL
SLICER_ENGINE_ORDER=bambu,prusa
SLICER_SLICE_TIMEOUT_SECONDS=600
SLICER_METADATA_HEADER_MAX_BYTES=6144
SLICER_MAX_MODEL_BYTES=268435456
```

Keep `slicer-base` under the `build` profile and keep normal image naming `dfpos-slicer:${DFPOS_IMAGE_TAG:-local}`.

**Step 4: Run config/static verification**

```bash
docker compose --env-file .env.example config --quiet
git diff --check -- services/slicer/Dockerfile.base services/slicer/Dockerfile docker-compose.yml .env.example
cd services/slicer && uv run --extra dev pytest -q app/tests/test_runtime_config.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add services/slicer/Dockerfile.base services/slicer/.dockerignore services/slicer/app/tests/test_runtime_config.py docker-compose.yml .env.example
git commit -m "build(slicer): pin Bambu Studio in local base"
```

If `.dockerignore` was not needed/created, omit it from `git add`.

---

### Task 11: Update operator and product-flow documentation

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `docs/product_creation_developer_flow.md`
- Modify: `TODO.md`

**Step 1: Update architecture**

Document that the system now has a dedicated slicer microservice in addition to audit/intelligence services, with Bambu/Prusa adapters and a future separate printer-gateway boundary. Correct the current statement that the project has only one supporting microservice.

**Step 2: Update the Add Product developer flow**

Replace Prusa-only text with:

- Bambu-first binary artifact flow.
- Exact fallback policy.
- Native `.gcode.3mf` versus estimate-only `.gcode` behavior.
- Engine metadata stored on `ProductAnalysisRun.slicer_stats_json`.
- Generated `ProductModelAsset` linkage.
- 0.4 mm matrix and honest multicolor limitation.

**Step 3: Add exact operator commands**

Document:

```bash
# Build the slow slicer runtime once (Bambu Studio + PrusaSlicer + Debian libraries)
docker build -f services/slicer/Dockerfile.base -t dfpos-slicer-base:local services/slicer

# Rebuild only application dependencies/code afterward
docker compose --env-file .env.example build slicer

# Run the normal stack without deleting database volumes
docker compose --env-file .env.example up -d
```

Also show the equivalent optional profile command:

```bash
docker compose --env-file .env.example --profile build build slicer-base
```

State explicitly that neither command requires volume deletion or `docker system prune --volumes`.

**Step 4: Mark TODO complete**

Change the Task 1 focus entry from `in-progress` to `done` and add the future printer-gateway/direct-print workflow to the parking lot, not this phase.

**Step 5: Check docs**

```bash
git diff --check -- ARCHITECTURE.md README.md docs/product_creation_developer_flow.md TODO.md
```

Expected: PASS.

**Step 6: Commit**

```bash
git add ARCHITECTURE.md README.md docs/product_creation_developer_flow.md TODO.md
git commit -m "docs: explain Bambu-primary product slicing"
```

---

### Task 12: Run full verification, including the one-time base build

**Files:**

- Modify only if a verification failure exposes an in-scope bug; return to the relevant task's RED/GREEN loop before editing.

**Step 1: Run service tests and lint**

```bash
cd services/slicer
uv run --extra dev pytest -q
cd /mnt/storage/docker/dfpos
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff check services/slicer
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff format --check services/slicer
```

Expected: all pass.

**Step 2: Run focused root tests**

```bash
cd /mnt/storage/docker/dfpos
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q \
  tests/test_model_analysis_slicer_client.py \
  tests/test_model_analysis_parser.py \
  tests/test_model_analysis_artifact_persistence.py \
  tests/test_product_asset_storage.py \
  tests/test_phase0_data_model.py \
  tests/test_phase2_analysis.py \
  tests/test_product_studio_model_upload.py \
  tests/test_phase4_ux.py
```

Expected: all pass.

**Step 3: Run repository-required checks**

```bash
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -v --tb=long
```

Expected: all pass. If unrelated pre-existing failures exist, report them separately with exact output and do not rewrite unrelated code.

**Step 4: Validate Compose and diffs**

```bash
docker compose --env-file .env.example config --quiet
git diff --check
git status -sb
```

Expected: valid Compose config, no whitespace errors, only intended changes/commits.

**Step 5: Build the slow base once**

```bash
docker build -f services/slicer/Dockerfile.base -t dfpos-slicer-base:local services/slicer
```

Expected: Bambu AppImage checksum passes, Bambu `--help` smoke check passes, and PrusaSlicer remains installed. This build can be slow and large once. If the Docker daemon is unavailable or progress stops without new output, stop and report the exact last output; do not perform destructive cleanup.

**Step 6: Verify both runtimes as non-root**

```bash
docker run --rm --user appuser dfpos-slicer-base:local /opt/bambu-studio/AppRun --help
docker run --rm --user appuser dfpos-slicer-base:local prusa-slicer --version
```

Expected: both exit zero and Bambu reports `02.07.01.62`.

**Step 7: Build the normal slicer twice**

```bash
docker compose --env-file .env.example build slicer
docker compose --env-file .env.example build slicer
```

Expected: both builds use `dfpos-slicer-base:local`; neither normal build contains an apt/Prusa/Bambu installation step. The second build should reuse application layers when inputs are unchanged.

**Step 8: Final evidence review**

```bash
git log --oneline --decorate -15
git status -sb
```

Confirm:

- Bambu is primary in tests/config/orchestrator.
- Prusa is fallback only and marked estimate-only.
- Add Product persists native artifacts and engine metadata.
- No migration or database reset was introduced.
- No Docker volume or database-data command was run.
- Going-forward build commands in docs are exact.

Do not create a final “verification fix” commit unless verification required an actual code/doc change.
