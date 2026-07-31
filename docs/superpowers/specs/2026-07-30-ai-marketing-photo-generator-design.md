# AI Marketing Photo Generator — Design Spec

- **Date:** 2026-07-30
- **Status:** Approved (pending spec review)
- **Origin:** `docs/Model_to_market_ready_photos.md`
- **Scope:** A single feature with four parts — an isolated FastAPI render microservice, backend depth extraction, dfpos Photo-Checklist + S3 integration, and a non-blocking studio UX.

## 1. Goal

Generate photorealistic marketing photos from a product's 3D model, on demand, for specific Photo Checklist shots, and link the result back to the checklist item via dfpos's existing S3 Object Service. The heavy compute runs on an isolated microservice deployed to a 2013 Mac Pro (Intel Xeon + AMD FirePro, CPU-only).

## 2. Constraints discovered during exploration

These shaped the design and diverge from the original `Model_to_market_ready_photos.md`:

1. **dfpos is Flask + Jinja2 + SQLAlchemy + Celery**, server-rendered with a post-redirect-get pattern — not FastAPI. `app/static/src/js/studio.js` already polls for long analysis jobs (the precedent for the "Generating…" badge).
2. **`<model-viewer>` cannot produce a depth map.** It exposes only `toDataURL()` (RGB), with no Z-buffer readback. Depth extraction therefore cannot happen in the current viewer. It moves to the backend (inside the microservice), computed from the mesh with `trimesh` (which dfpos already depends on).
3. **MPS is Apple-Silicon-only; the 2013 Mac Pro is Intel + AMD FirePro**, so the service runs **CPU-only with float32**. Each 512×512 render is multi-minute. This drives the async job model.
4. **`runwayml/stable-diffusion-v1-5` is gated on HuggingFace.** Default to the non-gated `stable-diffusion-v1-5/stable-diffusion-v1-5`; the gated `runwayml/…` remains selectable via env when an accepted license + `HF_TOKEN` are present. `lllyasviel/sd-controlnet-depth` is open.
5. **A sibling microservice architecture already exists to mirror:** `services/slicer/` (FastAPI, own Dockerfile, port 8092) + `app/services/slicer_client.py` (httpx, Bearer token) + config in `app/config.py` + a Celery task that orchestrates call → store → audit. The new ai-render service clones this pattern.

## 3. Decisions (from brainstorming)

- **Depth + render both happen inside the microservice.** dfpos sends the model file (multipart) + camera params + prompt + shot_id; the microservice computes the Z-depth map and runs ControlNet SD-1.5; returns a Base64 image.
- **Three AI-generatable shot types:** `hero`, `close_up`, `pos_tile`. The other four (`scale_in_hand`, `color_variants`, `packaging`, `booth_display`) keep their manual `image_reference` field with no AI button.
- **Auto-complete on success:** a successful render writes `image_reference` and sets `completed=True`. No separate review/accept gate. (An `ai_generated` flag is kept as informational metadata only.)
- **Prompt is automatic:** a per-shot template auto-filled from product name/material/category. No editable prompt field in v1.
- **Async job API** (POST `/generate` → 202 `{job_id}`; `GET /jobs/{id}` polled by the dfpos Celery task). The microservice processes one job at a time from an in-process serial queue.

## 4. Architecture

```
Product Studio (Flask)
  staff clicks "Generate with AI" on a hero/close_up/pos_tile shot row
  -> POST /products/studio/<pid>/photo-shot/<sid>/generate-ai  (ADMIN/STAFF)
     validates shot type + product has a model; sets ai_render_status=pending; audit
  -> Celery task render_product_photo_shot(shot_id)   (queue: ai_render, concurrency=1)
     1. build_prompt(shot_type, product)
     2. camera_for_shot(shot_type)
     3. resolve_model_bytes(product)  (GLB if converted_model_path else model_file_path)
     4. ai_render_client.create_generation(...)  -> {job_id}
     5. poll ai_render_client.get_job(job_id) until completed/failed
     6. on success: decode Base64 PNG ->
        upload_bytes_to_storage(bucket=PRODUCT_ASSETS_BUCKET,
          key="products/{pid}/renders/{shot_type}.png", content_type="image/png")
        -> s3 reference
     7. update shot: image_reference=ref, completed=True,
        ai_render_status=completed, ai_render_completed_at=now, ai_generated=True; audit
        on failure: ai_render_status=failed, ai_render_error=<msg>; audit
  -> ai-render microservice (FastAPI, on the 2013 Mac Pro, CPU-only)
     in-process serial job queue
     per job: load mesh (trimesh) -> raycast Z-depth at camera preset ->
       StableDiffusionControlNetPipeline (SD-1.5 + sd-controlnet-depth,
       cpu offload + attention slicing + float32) -> PNG -> Base64
  -> studio.js poller GET .../ai-status -> flips badge "Generating…" -> image
```

dfpos is free of heavy compute; all depth + diffusion runs on the Mac Pro. The `<model-viewer>` is left untouched.

## 5. Data model changes

One migration adding columns to `product_photo_shots` (mirrors how `Product` already carries `analysis_status`/`analysis_error`):

| Column | Type | Purpose |
|---|---|---|
| `ai_render_status` | Enum(`none`, `pending`, `running`, `completed`, `failed`), default `none`, indexed | drives the UI badge + status poll |
| `ai_render_error` | Text, nullable | surfaced on failure + retry |
| `ai_render_requested_at` | DateTime, nullable | timing/audit |
| `ai_render_completed_at` | DateTime, nullable | timing/audit |
| `ai_generated` | Boolean, default False | informational metadata that the image is AI-sourced (no gating) |

- New audit event `product_photo_shot.ai_generated` written via the existing audit helper in `app/services/product_ops.py`.
- `image_reference` (existing String(500)) holds the `s3://products/products/{pid}/renders/{shot_type}.png` reference on success.
- The launch-gate readiness math is unchanged beyond what `completed` already drives (`calculate_product_readiness` counts completed photo shots). `ai_generated` does not enter readiness.

## 6. Microservice contract — `services/ai-render/`

Async-backed, serial, jobs in-memory (a Mac Pro restart drops in-flight jobs → dfpos surfaces `failed` → user retries; acceptable for v1; future: Redis/disk-backed jobs).

### `POST /generate` (multipart, Bearer token) → `202`
Fields:
- `model_file` (file, required) — GLB/STL/OBJ
- `prompt` (str, required), `negative_prompt` (str), `shot_id` (str)
- `camera_az`, `camera_el`, `camera_dist`, `camera_fov` (floats)
- `width`, `height` (int), `steps` (int), `guidance` (float)

Returns `{ "job_id": "…" }`.

### `GET /jobs/{job_id}` → `200`
`{ "status": "queued"|"running"|"completed"|"failed", "image_base64": "…"(only when completed), "error": "…"(only when failed) }`.
`404` for unknown job (dfpos treats as `failed` → retry).

### Health (mirrors slicer)
- `GET /health/live`, `GET /health/ready` (ready = models loaded) so `ai_render_client.health_ready()` works identically to the slicer client.

### Camera presets (defaults, env-overridable)
- `hero` — az 35°, el 18°, dist=fit-bbox +10%, fov 35°
- `close_up` — az 30°, el 25°, dist=fit-bbox −35%, fov 28°
- `pos_tile` — az 0°, el 6°, dist=fit-bbox +25%, fov 40°

## 7. Depth extraction (inside the microservice, CPU-only)

- `trimesh.load` the model (GLB/STL/OBJ supported), center on bounding-box centroid, normalize to fit the camera.
- Pure-CPU raycast rasterizer (no GL/pyrender/OSMesa dependency — runs anywhere): one ray per output pixel through a pinhole camera at the shot's azimuth/elevation/fov; `trimesh.ray.intersects_first(origins, directions, multiple_hits=False)` → per-pixel hit distance = depth. Misses → background (max depth).
- Normalize depth to 0–1 PNG at the generation resolution (default 512×512). Cost ~262k rays against a BVH: a few seconds on the Mac Pro CPU, negligible vs. the SD step.

## 8. Diffusion pipeline (inside the microservice)

- `StableDiffusionControlNetPipeline.from_pretrained(SD15_REPO, controlnet=ControlNetModel.from_pretrained("lllyasviel/sd-controlnet-depth"))`, `torch_dtype=torch.float32`, loaded once at startup (lazy + lock on first request if startup-load is too slow).
- Hardware: `device = "mps" if torch.backends.mps.is_available() else "cpu"`, with try/except fallback to `cpu` on any MPS error (honors the spec's intent; the 2013 Mac Pro lands on `cpu`).
- Memory: `enable_model_cpu_offload()` + `enable_attention_slicing()`.
- Defaults: steps 30, guidance 7.5, negative prompt `"blurry, low quality, distorted, extra objects, text, watermark, deformed, oversaturated"`. All env-configurable.
- Model source: `SD15_REPO` defaults to `stable-diffusion-v1-5/stable-diffusion-v1-5` (non-gated); `runwayml/stable-diffusion-v1-5` selectable via env with `HF_TOKEN`. Local `HF_HOME`/pre-downloaded weights supported for the offline Mac Pro.

## 9. dfpos changes

### New files
- `app/services/ai_render_client.py` — httpx client mirroring `slicer_client.py`: `is_configured()`, `health_ready()`, `create_generation(model_bytes, filename, camera, prompt, shot_id, gen_params) -> job_id`, `get_job(job_id) -> dict`. Bearer token; generous timeout on create, short on poll. Config: `AI_RENDER_ENABLED`, `AI_RENDER_SERVICE_URL`, `AI_RENDER_INTERNAL_API_TOKEN`.
- `app/services/photo_render.py` — `build_prompt(shot_type, product)`, `camera_for_shot(shot_type)`, `resolve_model_bytes(product)`, `generate_shot(shot)` (client → poll → S3 upload → shot update + audit). Pure/testable; called by the task.
- `app/tasks/photo_render.py` — `render_product_photo_shot(shot_id)` Celery task on queue `ai_render` (concurrency 1): sets `running`, calls `generate_shot`, handles all failure paths.
- `migrations/versions/<alembic_revision_id>_photo_shot_ai_render.py` (revision id generated by Alembic at creation, down-revision = latest existing revision at implementation time).

### Modified files
- `app/models/product_ops.py` — new enum + columns; relationships unchanged.
- `app/services/product_ops.py` — extend `update_photo_shot` to persist `ai_render_*`; add `set_ai_render_status(shot, status, *, error=None, actor_id=None)`; emit `product_photo_shot.ai_generated` audit.
- `app/blueprints/products/studio_routes.py` — add `POST .../photo-shot/<sid>/generate-ai` (validates shot_type ∈ {hero, close_up, pos_tile}, product has model, AI render enabled; sets pending; enqueues task) and `GET .../photo-shot/<sid>/ai-status` (JSON for the poller).
- `app/templates/products/studio.html` — "Generate with AI" button on the 3 supported shot rows; badge/spinner when status pending/running; error + "Retry" when failed; render `image_reference` thumbnail when completed.
- `app/static/src/js/studio.js` — poller for shots in pending/running status hitting `ai-status`, updating the badge and swapping in the image (extends the existing analysis-poll pattern).
- `app/config.py`, `.env.example`, `docker-compose.yml` — new config keys + an example `ai-render` service block (Mac Pro is external in production, so URL/token are env overrides).

## 10. Error handling & retries

- Microservice unreachable / not configured → task sets `failed` with "AI render service unavailable"; UI shows Retry.
- Microservice returns `failed` (OOM, model-load error) → `failed`; error text surfaced.
- Poll `404`/timeout → `failed`; Retry.
- `Retry` re-enqueues the task (resets to pending). Concurrency=1 + the microservice serial queue prevent dogpiling.
- Storage upload failure → `failed` with error; image is not linked.
- All state transitions write audit. Launch-gate logic is untouched.

## 11. Testing (TDD)

### Microservice (`services/ai-render/tests/`)
- `depth.py`: known trimesh primitive (e.g., sphere) → depth map has correct shape, expected silhouette, monotonic depth; camera param variations.
- Job lifecycle with a **stub pipeline** (monkeypatch the SD pipeline to return a fixed `PIL.Image`) — never loads real models in CI: queued → running → completed → base64 round-trip; failure path.
- `/generate` + `/jobs/{id}` + `/health/*` contract tests (multipart parsing, auth, 404).

### dfpos (`tests/`)
- `photo_render.build_prompt` per shot_type + product → expected string; `camera_for_shot` returns presets.
- `ai_render_client` with mocked httpx transport (create → job_id, poll → completed/failed, not-configured).
- The Celery task with a mocked client: success → S3 upload (mocked) + `image_reference` set + `completed=True` + `ai_render_status=completed` + audit; failure → `failed` + error; service-disabled → graceful `failed`.
- Route tests: role guard, rejects non-AI shot types, rejects product-without-model, enqueues exactly once; `ai-status` returns correct JSON per status.
- Migration test: new columns exist; default `ai_render_status='none'`.

### Integration
- End-to-end smoke with the microservice stub pipeline + local storage backend → `image_reference` populated.

## 12. Out of scope (v1) / future

- Editable per-shot prompt field.
- Redis- or disk-backed job store on the microservice (survives restarts).
- Aspect ratios other than square 512×512.
- AI generation for `scale_in_hand`, `color_variants`, `packaging`, `booth_display`.
- Wiring the slicer's currently-stubbed `/api/v1/slice` route (pre-existing gap, unrelated to this feature).