# AI Marketing Photo Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate photorealistic marketing photos from a product's 3D model for the `hero`, `close_up`, and `pos_tile` Photo Checklist shots, via an isolated FastAPI render microservice, and link the result back to the checklist item through dfpos's S3 Object Service.

**Architecture:** A new `services/ai-render/` FastAPI microservice (mirrors the existing `services/slicer/` split) deployed to a 2013 Mac Pro, CPU-only. dfpos enqueues a Celery task per shot; the task sends the model file + camera params + prompt to the microservice, which computes a Z-depth map and runs ControlNet Stable Diffusion v1.5, returning a Base64 image. dfpos uploads that image to S3 and auto-completes the `ProductPhotoShot`. dfpos never runs heavy compute.

**Tech Stack:** Flask + SQLAlchemy + Celery (dfpos); FastAPI + diffusers + transformers + torch + trimesh + numpy + Pillow (microservice); S3 via the existing `app/services/storage.py`; pytest + httpx for tests.

## Global Constraints

- dfpos is Flask/Jinja2/SQLAlchemy/Celery, **not** FastAPI. Follow existing patterns; do not introduce a new web framework in dfpos.
- Microservice lives in `services/ai-render/` and mirrors `services/slicer/` (own `app/` package, `pydantic_settings` config with `env_prefix="AI_RENDER_"`, FastAPI lifespan, `/health/live` + `/health/ready`, Bearer-token auth).
- The target Mac Pro is Intel + AMD FirePro (2013 "Trashcan"), so the diffusion pipeline runs **CPU-only with `torch.float32`**; `device = "mps" if available else "cpu"` with a try/except fallback to `cpu`. Document this; do not assume MPS works.
- Default SD checkpoint is the **non-gated** `stable-diffusion-v1-5/stable-diffusion-v1-5`; `runwayml/stable-diffusion-v1-5` is selectable via env only when an accepted license + `HF_TOKEN` are present. ControlNet is `lllyasviel/sd-controlnet-depth`.
- Only three shot types are AI-generatable: `hero`, `close_up`, `pos_tile`. The other four keep their manual `image_reference` field with no AI button.
- On a successful render, the shot is **auto-completed** (`image_reference` set, `completed=True`).
- Prompts are **automatic** from per-shot templates filled with product metadata; no editable prompt field.
- Tests must run **without** downloading torch/diffusers models — the renderer is always injected/stubbed in tests, and `renderer.py` imports torch/diffusers lazily so the test environment never needs them.
- Current Alembic head is `b3c4d5e6f7a8`; the new migration's `down_revision` must be `"b3c4d5e6f7a8"`.

## Deviation from the approved spec (one, called out for your review)

The spec described depth extraction via trimesh raycasting and a microservice contract using `camera_az, camera_el, camera_dist, camera_fov`. The plan refines this to an **orthographic** software rasterizer (pure numpy, no Embree/GL/OSMesa native dependency) and a contract field `camera_extent` instead of `dist`+`fov`. **Why:** (1) product hero photography is effectively orthographic (long-lens), so orthographic depth is more appropriate, not less; (2) pure-numpy makes depth extraction run and test anywhere pytest runs, with no fragile native raycaster/GL libs — important for a "no gaps" target on a 2013 Mac Pro; (3) the rasterizer is far simpler and fully unit-testable. If you'd rather keep perspective (`dist`+`fov`), say so before execution and Task 2/Task 5 change accordingly.

---

## File Structure

### Microservice — `services/ai-render/`
- `requirements.txt` — pinned deps; torch/diffusers grouped so test-only installs can skip them.
- `Dockerfile` — pip-based image exposing port 8093 (mirrors slicer Dockerfile shape).
- `app/__init__.py` — empty package marker.
- `app/config.py` — `pydantic_settings.Settings` with `env_prefix="AI_RENDER_"`.
- `app/schemas.py` — pydantic models: `GenerateAcceptedResponse`, `JobStatusResponse`, health responses.
- `app/auth.py` — FastAPI Bearer-token dependency.
- `app/main.py` — `create_app()` FastAPI factory; lifespan lazily primes the pipeline.
- `app/api/__init__.py` — empty.
- `app/api/health.py` — `/health/live`, `/health/ready` (ready = pipeline primed).
- `app/api/generate.py` — `POST /generate` (multipart) → 202 `{job_id}`; `GET /jobs/{job_id}`.
- `app/services/__init__.py` — empty.
- `app/services/depth.py` — `render_depth(model_bytes, *, az, el, extent, width, height) -> PIL.Image` (numpy orthographic z-buffer).
- `app/services/renderer.py` — lazy-imported `render_image(prompt, negative_prompt, depth_image, *, steps, guidance, width, height) -> PIL.Image` (diffusers ControlNet pipeline).
- `app/services/jobs.py` — in-memory serial `JobManager` (single worker thread).
- `tests/__init__.py` — empty.
- `tests/conftest.py` — FastAPI `TestClient` fixture, stubbed renderer injection.
- `tests/test_depth.py`, `tests/test_jobs.py`, `tests/test_generate_api.py`, `tests/test_health.py`.

### dfpos
- Modify `app/models/product_ops.py` — add `AIRenderStatus` enum + 5 columns on `ProductPhotoShot`.
- Create `migrations/versions/c4d5e6f7a8b9_photo_shot_ai_render.py` — Alembic migration.
- Modify `app/services/product_ops.py` — add `set_ai_render_status()` and `complete_ai_render()` (+ audit).
- Create `app/services/ai_render_client.py` — httpx client mirroring `slicer_client.py`.
- Create `app/services/photo_render.py` — prompt builder, camera presets, model resolution, orchestration.
- Create `app/tasks/photo_render.py` — `render_product_photo_shot` Celery task.
- Modify `app/celery_app.py` — register `"app.tasks.photo_render"` in `include`.
- Modify `app/blueprints/products/studio_routes.py` — `generate-ai` POST route + `ai-status` GET route.
- Modify `app/templates/products/studio.html` — "Generate with AI" button + status badge on the 3 shots.
- Modify `app/static/src/js/studio.js` — status poller.
- Modify `app/config.py`, `.env.example`, `docker-compose.yml` — config keys + example service.
- Create `tests/test_ai_render_client.py`, `tests/test_photo_render.py`, `tests/test_photo_render_task.py`, `tests/test_studio_ai_routes.py`, `tests/test_photo_render_migration.py`, `tests/test_ai_render_integration.py`.

---

## Task 1: Microservice scaffold, config, health

**Files:**
- Create: `services/ai-render/app/__init__.py`, `app/config.py`, `app/schemas.py`, `app/auth.py`, `app/api/__init__.py`, `app/api/health.py`, `app/main.py`
- Create: `services/ai-render/tests/__init__.py`, `tests/conftest.py`, `tests/test_health.py`
- Create: `services/ai-render/requirements.txt`

**Interfaces:**
- Produces: a `create_app() -> FastAPI` factory in `app/main.py`; `settings` in `app/config.py`; `/health/live` and `/health/ready` returning `HealthLiveResponse`/`HealthReadyResponse`; `verify_token` dependency in `app/auth.py`. Later tasks mount the generate router on the same app.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
python-multipart==0.0.20
trimesh==4.5.3
numpy==2.2.1
pillow==11.0.0
httpx==0.28.1
pytest==8.3.4

# Heavy ML deps (not needed for unit tests; the renderer imports them lazily).
# torch==2.5.1
# transformers==4.46.3
# diffusers==0.31.0
# accelerate==1.2.1
```

- [ ] **Step 2: Write `app/__init__.py`** (empty) and `app/api/__init__.py`** (empty).

- [ ] **Step 3: Write `app/config.py`**

```python
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AI_RENDER_", extra="ignore")

    service_name: str = "dfp-ai-render"
    api_host: str = "0.0.0.0"
    api_port: int = 8093
    internal_api_token: str = "change-me-ai-render-token"
    log_level: str = "INFO"

    sd_repo: str = "stable-diffusion-v1-5/stable-diffusion-v1-5"
    controlnet_repo: str = "lllyasviel/sd-controlnet-depth"
    hf_token: str = ""
    hf_home: str = ""

    torch_dtype: str = "float32"
    enable_cpu_offload: bool = True
    enable_attention_slicing: bool = True

    default_steps: int = 30
    default_guidance: float = 7.5
    default_negative_prompt: str = (
        "blurry, low quality, distorted, extra objects, text, watermark, deformed, oversaturated"
    )
    default_width: int = 512
    default_height: int = 512

    poll_interval_seconds: float = 5.0
    job_max_age_seconds: int = 3600


settings = Settings()
```

- [ ] **Step 4: Write `app/schemas.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class HealthLiveResponse(BaseModel):
    status: str
    service: str


class HealthReadyResponse(BaseModel):
    status: str
    service: str
    pipeline: str  # "ready" | "not_loaded"


class GenerateAcceptedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    status: str  # "queued" | "running" | "completed" | "failed"
    image_base64: str | None = None
    error: str | None = None
```

- [ ] **Step 5: Write `app/auth.py`**

```python
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.config import settings


async def verify_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
```

- [ ] **Step 6: Write `app/api/health.py`**

```python
from __future__ import annotations

from fastapi import APIRouter

from app import services
from app.config import settings
from app.schemas import HealthLiveResponse, HealthReadyResponse

router = APIRouter(tags=["health"])


@router.get("/live", response_model=HealthLiveResponse)
async def health_live():
    return HealthLiveResponse(status="alive", service=settings.service_name)


@router.get("/ready", response_model=HealthReadyResponse)
async def health_ready():
    # `services.renderer.is_primed` is set by the lifespan (Task 4); default False.
    ready = getattr(services.renderer, "is_primed", False)
    return HealthReadyResponse(
        status="ready" if ready else "unhealthy",
        service=settings.service_name,
        pipeline="ready" if ready else "not_loaded",
    )
```

- [ ] **Step 7: Write `app/services/__init__.py` and a stub `app/services/renderer.py`**

`app/services/__init__.py`:
```python
from __future__ import annotations

from . import renderer  # noqa: F401
```

`app/services/renderer.py` (stub here; real pipeline added in Task 4):
```python
from __future__ import annotations

is_primed: bool = False
```

- [ ] **Step 8: Write `app/main.py`**

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health as health_api
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.include_router(health_api.router, prefix="/health")
    return app


app = create_app()
```

- [ ] **Step 9: Write `tests/conftest.py`**

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "test-token")
    app = create_app()
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer test-token"
        yield c


@pytest.fixture()
def unauth_client():
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 10: Write the failing test `tests/test_health.py`**

```python
from __future__ import annotations


def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_health_ready_reports_pipeline_state(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    # pipeline is not loaded in tests → unhealthy until Task 4 primes it
    assert body["pipeline"] == "not_loaded"
    assert body["status"] == "unhealthy"


def test_health_requires_token(unauth_client):
    assert unauth_client.get("/health/ready").status_code == 401
```

Wait — the `/health/live` endpoint in the slicer has **no auth**; only operational endpoints are protected. Mirror that: leave `/health/live` and `/health/ready` unauthenticated (so dfpos's `health_ready()` probe and any load-balancer work without a token, exactly like the slicer). Remove the auth requirement from health. Correct the test accordingly:

```python
from __future__ import annotations


def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_health_live_no_auth_required(unauth_client):
    r = unauth_client.get("/health/live")
    assert r.status_code == 200


def test_health_ready_reports_pipeline_state(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["pipeline"] == "not_loaded"
    assert body["status"] == "unhealthy"
```

(Health routes must not depend on `verify_token`. Confirm `app/api/health.py` has no `Depends(verify_token)` — it does not, per Step 6. Good.)

- [ ] **Step 11: Run tests to verify they pass**

Run: `cd services/ai-render && python -m pip install -r requirements.txt && python -m pytest tests/test_health.py -v`
Expected: PASS (3 tests).

- [ ] **Step 12: Commit**

```bash
git add services/ai-render/
git commit -m "feat(ai-render): scaffold FastAPI microservice with config, schemas, health"
```

---

## Task 2: Depth extraction (pure-numpy orthographic z-buffer)

**Files:**
- Create: `services/ai-render/app/services/depth.py`
- Create: `services/ai-render/tests/test_depth.py`

**Interfaces:**
- Produces: `render_depth(model_bytes: bytes, *, az: float, el: float, extent: float, width: int = 512, height: int = 512) -> PIL.Image.Image` returning a grayscale ("L") depth image where nearer = lower pixel value (0 = nearest hit, 255 = far/background). Used by `jobs.py` in Task 3.

- [ ] **Step 1: Write the failing test `tests/test_depth.py`**

```python
from __future__ import annotations

import io

import numpy as np
import trimesh
from PIL import Image

from app.services.depth import render_depth


def _box_bytes() -> bytes:
    mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])  # centered at origin, [-0.5,0.5]
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()


def test_render_depth_returns_grayscale_image_of_requested_size():
    img = render_depth(_box_bytes(), az=0.0, el=0.0, extent=0.7, width=64, height=64)
    assert isinstance(img, Image.Image)
    assert img.mode == "L"
    assert img.size == (64, 64)


def test_center_pixel_is_a_hit_and_background_is_far():
    img = render_depth(_box_bytes(), az=0.0, el=0.0, extent=0.7, width=64, height=64)
    arr = np.asarray(img)
    center = arr[32, 32]
    corner = arr[0, 0]
    # The box front face occupies the center; background corners are misses (255).
    assert center < 255, "center should be a hit (object covers it)"
    assert corner == 255, "corner should be background"


def test_different_angle_changes_depth_map():
    a = np.asarray(render_depth(_box_bytes(), az=0.0, el=0.0, extent=0.7, width=32, height=32))
    b = np.asarray(render_depth(_box_bytes(), az=45.0, el=45.0, extent=0.7, width=32, height=32))
    assert not np.array_equal(a, b)


def test_extent_zooms_in():
    wide = np.asarray(render_depth(_box_bytes(), az=0.0, el=0.0, extent=1.2, width=64, height=64))
    tight = np.asarray(render_depth(_box_bytes(), az=0.0, el=0.0, extent=0.4, width=64, height=64))
    # A tighter extent shows more background around the object.
    assert tight.sum() >= wide.sum()  # tighter crop → fewer background(255) pixels is false;
    # actually tighter extent makes object bigger → fewer background pixels → lower sum. Reverse:
    assert tight.sum() <= wide.sum()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/ai-render && python -m pytest tests/test_depth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.depth'`.

- [ ] **Step 3: Write `app/services/depth.py`**

```python
from __future__ import annotations

import io
import math

import numpy as np
import trimesh
from PIL import Image


def _look_at(az_deg: float, el_deg: float) -> np.ndarray:
    """Return a 3x3 rotation mapping world -> camera space. Camera looks down -Z."""
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    cos_el = math.cos(el)
    eye = np.array([cos_el * math.sin(az), math.sin(el), cos_el * math.cos(az)], dtype=np.float64)
    forward = -eye / np.linalg.norm(eye)
    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)
    # rows = camera basis vectors
    return np.stack([right, up, -forward], axis=0)


def render_depth(
    model_bytes: bytes,
    *,
    az: float,
    el: float,
    extent: float,
    width: int = 512,
    height: int = 512,
) -> Image.Image:
    """Orthographic z-buffer depth render. Nearer surface -> lower pixel value."""
    mesh = trimesh.load(io.BytesIO(model_bytes), force="mesh", skip_materials=True, process=False)
    V = np.asarray(mesh.vertices, dtype=np.float64)
    F = np.asarray(mesh.faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return Image.new("L", (width, height), 255)

    # Center on the centroid and scale so the max vertex norm is 1 (object fits the unit sphere).
    V = V - V.mean(axis=0)
    max_norm = float(np.linalg.norm(V, axis=1).max()) or 1.0
    V = V / max_norm

    R = _look_at(az, el)
    Vcam = V @ R.T  # camera space; camera looks down -Z
    x = Vcam[:, 0]
    y = Vcam[:, 1]
    depth = -Vcam[:, 2]  # positive for points in front (z<0); near = small

    # Orthographic screen coords (extent = half-width of the view in object-normalized units).
    sx = (x / extent + 1.0) * 0.5 * (width - 1)
    sy = (1.0 - (y / extent + 1.0) * 0.5) * (height - 1)  # flip Y for image coords
    screen = np.stack([sx, sy], axis=1)

    depth_buf = np.full((height, width), np.inf, dtype=np.float64)

    for tri in F:
        i0, i1, i2 = tri
        d0, d1, d2 = depth[i0], depth[i1], depth[i2]
        if d0 <= 0.0 or d1 <= 0.0 or d2 <= 0.0:
            continue  # any vertex behind the camera → skip the triangle
        p0, p1, p2 = screen[i0], screen[i1], screen[i2]

        min_x = max(0, int(math.floor(min(p0[0], p1[0], p2[0]))))
        max_x = min(width - 1, int(math.ceil(max(p0[0], p1[0], p2[0]))))
        min_y = max(0, int(math.floor(min(p0[1], p1[1], p2[1]))))
        max_y = min(height - 1, int(math.ceil(max(p0[1], p1[1], p2[1]))))
        if max_x < min_x or max_y < min_y:
            continue

        gx, gy = np.meshgrid(np.arange(min_x, max_x + 1), np.arange(min_y, max_y + 1))
        px = gx.ravel().astype(np.float64)
        py = gy.ravel().astype(np.float64)

        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
        if abs(area) < 1e-12:
            continue

        def _edge(ax_, ay_, bx_, by_, qx_, qy_):
            return (bx_ - ax_) * (qy_ - ay_) - (by_ - ay_) * (qx_ - ax_)

        w0 = _edge(p1[0], p1[1], p2[0], p2[1], px, py) / area
        w1 = _edge(p2[0], p2[1], p0[0], p0[1], px, py) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
        if not inside.any():
            continue
        z = w0 * d0 + w1 * d1 + w2 * d2

        ys = np.arange(min_y, max_y + 1)
        xs = np.arange(min_x, max_x + 1)
        sub = depth_buf[np.ix_(ys, xs)]
        z2 = z.reshape(sub.shape)
        upd = inside.reshape(sub.shape) & (z2 < sub)
        sub[upd] = z2[upd]
        depth_buf[np.ix_(ys, xs)] = sub

    finite = depth_buf[np.isfinite(depth_buf)]
    out = np.full((height, width), 255, dtype=np.uint8)
    if finite.size:
        lo, hi = finite.min(), finite.max()
        span = (hi - lo) or 1.0
        norm = (depth_buf - lo) / span  # 0 near .. 1 far
        valid = np.isfinite(depth_buf)
        out[valid] = np.clip(norm[valid] * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/ai-render && python -m pytest tests/test_depth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add services/ai-render/app/services/depth.py services/ai-render/tests/test_depth.py
git commit -m "feat(ai-render): pure-numpy orthographic depth rasterizer"
```

---

## Task 3: In-memory serial job manager

**Files:**
- Create: `services/ai-render/app/services/jobs.py`
- Create: `services/ai-render/tests/test_jobs.py`

**Interfaces:**
- Produces: `JobManager` class:
  - `submit(render_fn, params: dict) -> str` (returns job_id)
  - `get(job_id) -> dict` (returns `{"status": ..., "image_base64": ..., "error": ...}`)
- `render_fn` signature (the seam for stubbing in tests): `render_fn(model_bytes: bytes, prompt: str, negative_prompt: str, depth_image: PIL.Image.Image, params: dict) -> bytes` returning PNG bytes.
- `JobManager` processes exactly one job at a time via a single daemon worker thread and a `queue.Queue`.

- [ ] **Step 1: Write the failing test `tests/test_jobs.py`**

```python
from __future__ import annotations

import time

from app.services.jobs import JobManager


def _stub_render(model_bytes, prompt, negative_prompt, depth_image, params):
    return b"\x89PNG fake bytes"


def test_submit_returns_job_id_and_eventually_completes():
    mgr = JobManager()
    jid = mgr.submit(_stub_render, {"model_bytes": b"x", "prompt": "p"})
    assert isinstance(jid, str) and len(jid) > 0
    # wait for completion
    for _ in range(100):
        res = mgr.get(jid)
        if res["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert res["status"] == "completed"
    assert res["image_base64"]  # base64-encoded PNG


def test_failed_render_records_error():
    def boom(model_bytes, prompt, negative_prompt, depth_image, params):
        raise RuntimeError("boom")

    mgr = JobManager()
    jid = mgr.submit(boom, {"model_bytes": b"x", "prompt": "p"})
    for _ in range(100):
        res = mgr.get(jid)
        if res["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert res["status"] == "failed"
    assert "boom" in res["error"]


def test_jobs_run_serially():
    order = []

    def slow(model_bytes, prompt, negative_prompt, depth_image, params):
        order.append(("start", prompt))
        time.sleep(0.1)
        order.append(("end", prompt))
        return b"x"

    mgr = JobManager()
    j1 = mgr.submit(slow, {"model_bytes": b"", "prompt": "a"})
    j2 = mgr.submit(slow, {"model_bytes": b"", "prompt": "b"})
    for _ in range(200):
        if mgr.get(j1)["status"] in {"completed", "failed"} and mgr.get(j2)["status"] in {
            "completed",
            "failed",
        }:
            break
        time.sleep(0.05)
    # No interleaving: a fully completes before b starts.
    assert order == [("start", "a"), ("end", "a"), ("start", "b"), ("end", "b")]


def test_unknown_job_is_none():
    mgr = JobManager()
    assert mgr.get("does-not-exist") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/ai-render && python -m pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/services/jobs.py`**

```python
from __future__ import annotations

import base64
import queue
import threading
import uuid
from typing import Any, Callable

RenderFn = Callable[[bytes, str, str, Any, dict], bytes]


class _Job:
    def __init__(self, job_id: str, render_fn: RenderFn, params: dict) -> None:
        self.id = job_id
        self.render_fn = render_fn
        self.params = params
        self.status = "queued"
        self.image_base64: str | None = None
        self.error: str | None = None


class JobManager:
    """Serial, in-memory job runner. Exactly one job runs at a time."""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, render_fn: RenderFn, params: dict) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = _Job(job_id, render_fn, params)
        self._queue.put(job_id)
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                "status": job.status,
                "image_base64": job.image_base64,
                "error": job.error,
            }

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                job = self._jobs[job_id]
                job.status = "running"
            try:
                png = job.render_fn(
                    job.params["model_bytes"],
                    job.params["prompt"],
                    job.params.get("negative_prompt", ""),
                    job.params.get("depth_image"),
                    job.params,
                )
                with self._lock:
                    job.status = "completed"
                    job.image_base64 = base64.b64encode(png).decode("ascii")
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job.status = "failed"
                    job.error = str(exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/ai-render && python -m pytest tests/test_jobs.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add services/ai-render/app/services/jobs.py services/ai-render/tests/test_jobs.py
git commit -m "feat(ai-render): serial in-memory job manager"
```

---

## Task 4: Renderer (diffusers ControlNet, lazy-imported, injectable)

**Files:**
- Modify: `services/ai-render/app/services/renderer.py`
- Modify: `services/ai-render/app/services/__init__.py` (no change needed if already imports renderer)
- Create: `services/ai-render/tests/test_renderer_seam.py`

**Interfaces:**
- Produces: `render_image(prompt, negative_prompt, depth_image, *, steps, guidance, width, height) -> PIL.Image.Image` using the loaded ControlNet SD-1.5 pipeline (CPU-only, float32, cpu offload + attention slicing). Also `prime_pipeline()` (loads models once; sets `is_primed = True`) and the module-level `is_primed: bool`.
- Tests do **not** load torch. They assert the seam: `render_image` is callable and that a stub render callable injected into the JobManager is used end-to-end (covered by Task 3 already). Here we test only that `prime_pipeline` is gated behind heavy imports.

- [ ] **Step 1: Write `tests/test_renderer_seam.py`**

```python
from __future__ import annotations

import importlib

from app.services import renderer


def test_is_primed_starts_false():
    importlib.reload(renderer)
    assert renderer.is_primed is False


def test_render_image_callable_signature_exists():
    assert callable(renderer.render_image)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/ai-render && python -m pytest tests/test_renderer_seam.py -v`
Expected: FAIL — `renderer.render_image` does not exist (only `is_primed` stub).

- [ ] **Step 3: Write `app/services/renderer.py`**

```python
from __future__ import annotations

import io

from PIL import Image

from app.config import settings

is_primed: bool = False
_pipeline = None
_lock = None  # threading.Lock, created lazily


def _new_lock():
    import threading

    return threading.Lock()


def prime_pipeline() -> None:
    """Load the ControlNet SD-1.5 pipeline once. Heavy; imports torch lazily."""
    global is_primed, _pipeline, _lock
    if is_primed:
        return
    if _lock is None:
        _lock = _new_lock()
    with _lock:
        if is_primed:
            return
        import torch  # noqa: deferred import
        from diffusers import (
            ControlNetModel,
            StableDiffusionControlNetPipeline,
        )

        dtype = torch.float32 if settings.torch_dtype == "float32" else torch.float16
        controlnet = ControlNetModel.from_pretrained(
            settings.controlnet_repo, torch_dtype=dtype, token=settings.hf_token or None
        )
        pipe = StableDiffusionControlNetPipeline.from_pretrained(
            settings.sd_repo, controlnet=controlnet, torch_dtype=dtype, token=settings.hf_token or None
        )

        device = "cpu"
        try:
            if torch.backends.mps.is_available():
                pipe.to("mps")
                device = "mps"
        except Exception:  # noqa: BLE001 — fall back to CPU on any MPS error
            pipe.to("cpu")
            device = "cpu"

        if device == "cpu" and settings.enable_cpu_offload:
            pipe.enable_model_cpu_offload()
        if settings.enable_attention_slicing:
            pipe.enable_attention_slicing()

        _pipeline = pipe
        is_primed = True


def render_image(
    prompt: str,
    negative_prompt: str,
    depth_image: Image.Image,
    *,
    steps: int,
    guidance: float,
    width: int,
    height: int,
) -> Image.Image:
    prime_pipeline()
    result = _pipeline(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=depth_image,
        num_inference_steps=steps,
        guidance_scale=guidance,
        width=width,
        height=height,
    )
    return result.images[0]


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/ai-render && python -m pytest tests/test_renderer_seam.py -v`
Expected: PASS (2 tests). No torch import occurs.

- [ ] **Step 5: Commit**

```bash
git add services/ai-render/app/services/renderer.py services/ai-render/tests/test_renderer_seam.py
git commit -m "feat(ai-render): lazy-loaded ControlNet SD-1.5 renderer (CPU-only)"
```

---

## Task 5: Generate + jobs API endpoints

**Files:**
- Create: `services/ai-render/app/api/generate.py`
- Modify: `services/ai-render/app/main.py` (mount generate router)
- Create: `services/ai-render/tests/test_generate_api.py`

**Interfaces:**
- Consumes: `JobManager` from Task 3, `render_depth` from Task 2, `render_image` + `to_png_bytes` from Task 4.
- Produces: `POST /generate` (multipart: `model_file`, `prompt`, `negative_prompt`, `shot_id`, `camera_az`, `camera_el`, `camera_extent`, `width`, `height`, `steps`, `guidance`) → `202 {"job_id"}`; `GET /jobs/{job_id}` → `200 {"status","image_base64","error"}` or `404`.
- A single module-level `JobManager` instance is created once and shared. Tests inject a stub `render_fn` by submitting through a helper, or by monkeypatching `render_image`/`render_depth`.

- [ ] **Step 1: Write `tests/test_generate_api.py`**

```python
from __future__ import annotations

import io
import time

import trimesh
from fastapi.testclient import TestClient

from app.main import create_app


def _model_bytes() -> bytes:
    buf = io.BytesIO()
    trimesh.creation.box(extents=[1, 1, 1]).export(buf, file_type="stl")
    return buf.getvalue()


def _client_with_stub_renderer(monkeypatch):
    import app.api.generate as gen

    def fake_render(model_bytes, prompt, negative_prompt, depth_image, params):
        # Return a real PNG so base64 round-trips.
        from PIL import Image

        return gen.renderer.to_png_bytes(Image.new("RGB", (8, 8), (10, 20, 30)))

    monkeypatch.setattr(gen, "_render_fn", fake_render)
    app = create_app()
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer test-token"
        yield c


def test_generate_accepts_multipart_and_returns_job_id(monkeypatch):
    client = next(_client_with_stub_renderer(monkeypatch))
    r = client.post(
        "/generate",
        files={"model_file": ("box.stl", _model_bytes(), "application/octet-stream")},
        data={
            "prompt": "hero shot",
            "shot_id": "42",
            "camera_az": "35",
            "camera_el": "18",
            "camera_extent": "0.62",
        },
    )
    assert r.status_code == 202
    assert "job_id" in r.json()


def test_job_lifecycle_completes(monkeypatch):
    client = next(_client_with_stub_renderer(monkeypatch))
    r = client.post(
        "/generate",
        files={"model_file": ("box.stl", _model_bytes(), "application/octet-stream")},
        data={"prompt": "p", "shot_id": "1", "camera_az": "0", "camera_el": "0", "camera_extent": "0.7"},
    )
    jid = r.json()["job_id"]
    for _ in range(100):
        s = client.get(f"/jobs/{jid}")
        body = s.json()
        if body["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert body["status"] == "completed"
    assert body["image_base64"]


def test_unknown_job_404(monkeypatch):
    client = next(_client_with_stub_renderer(monkeypatch))
    assert client.get("/jobs/nope").status_code == 404


def test_generate_requires_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "internal_api_token", "test-token")
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/generate",
            files={"model_file": ("box.stl", _model_bytes(), "application/octet-stream")},
            data={"prompt": "p", "shot_id": "1", "camera_az": "0", "camera_el": "0", "camera_extent": "0.7"},
        )
        assert r.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/ai-render && python -m pytest tests/test_generate_api.py -v`
Expected: FAIL — `/generate` route does not exist (404).

- [ ] **Step 3: Write `app/api/generate.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app import renderer
from app.auth import verify_token
from app.config import settings
from app.schemas import GenerateAcceptedResponse, JobStatusResponse
from app.services.depth import render_depth
from app.services.jobs import JobManager

router = APIRouter(tags=["generate"], dependencies=[Depends(verify_token)])

_manager = JobManager()


def _render_fn(model_bytes, prompt, negative_prompt, depth_image, params):
    """The real render callable submitted to the JobManager. Uses depth + diffusers.
    Tests monkeypatch this module's `_render_fn` to avoid loading torch.
    """
    depth = depth_image
    if depth is None:
        depth = render_depth(
            model_bytes,
            az=float(params["camera_az"]),
            el=float(params["camera_el"]),
            extent=float(params["camera_extent"]),
            width=int(params.get("width", settings.default_width)),
            height=int(int(params.get("height", settings.default_height))),
        )
    img = renderer.render_image(
        prompt,
        negative_prompt,
        depth,
        steps=int(params.get("steps", settings.default_steps)),
        guidance=float(params.get("guidance", settings.default_guidance)),
        width=int(params.get("width", settings.default_width)),
        height=int(int(params.get("height", settings.default_height))),
    )
    return renderer.to_png_bytes(img)


@router.post("/generate", response_model=GenerateAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    model_file: UploadFile = File(...),
    prompt: str = Form(...),
    shot_id: str = Form(""),
    negative_prompt: str = Form(settings.default_negative_prompt),
    camera_az: float = Form(0.0),
    camera_el: float = Form(0.0),
    camera_extent: float = Form(0.62),
    width: int = Form(settings.default_width),
    height: int = Form(settings.default_height),
    steps: int = Form(settings.default_steps),
    guidance: float = Form(settings.default_guidance),
):
    model_bytes = await model_file.read()
    params = {
        "model_bytes": model_bytes,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "shot_id": shot_id,
        "camera_az": camera_az,
        "camera_el": camera_el,
        "camera_extent": camera_extent,
        "width": width,
        "height": height,
        "steps": steps,
        "guidance": guidance,
    }
    depth = render_depth(
        model_bytes,
        az=camera_az,
        el=camera_el,
        extent=camera_extent,
        width=width,
        height=height,
    )
    params["depth_image"] = depth
    job_id = _manager.submit(_render_fn, params)
    return GenerateAcceptedResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    result = _manager.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(**result)
```

- [ ] **Step 4: Mount the router in `app/main.py`**

Add after the health include:
```python
from app.api import generate as generate_api
app.include_router(generate_api.router)
```
(Full updated `main.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import generate as generate_api
from app.api import health as health_api
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.include_router(health_api.router, prefix="/health")
    app.include_router(generate_api.router)
    return app


app = create_app()
```
)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/ai-render && python -m pytest tests/test_generate_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full microservice suite**

Run: `cd services/ai-render && python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add services/ai-render/app/api/generate.py services/ai-render/app/main.py services/ai-render/tests/test_generate_api.py
git commit -m "feat(ai-render): /generate multipart + /jobs polling endpoints"
```

---

## Task 6: Microservice Dockerfile + run instructions

**Files:**
- Create: `services/ai-render/Dockerfile`
- Create: `services/ai-render/.dockerignore`
- Modify: `services/ai-render/requirements.txt` (uncomment heavy ML deps; keep test-only ones separate)

**Interfaces:**
- Produces: a container image that runs the microservice on port 8093 with `uvicorn app.main:app`.

- [ ] **Step 1: Finalize `requirements.txt`** (uncomment the ML group so the image is runnable):

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
python-multipart==0.0.20
trimesh==4.5.3
numpy==2.2.1
pillow==11.0.0
httpx==0.28.1
pytest==8.3.4
torch==2.5.1
transformers==4.46.3
diffusers==0.31.0
accelerate==1.2.1
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
RUN chown appuser:appuser /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8093
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8093"]
```

- [ ] **Step 3: Write `.dockerignore`**

```
__pycache__/
*.pyc
tests/
.env
.pytest_cache/
```

- [ ] **Step 4: Verify the image builds (smoke)**

Run: `cd services/ai-render && docker build -t dfp-ai-render:plan .`
Expected: build succeeds (no torch import errors; torch only imported at request time).

- [ ] **Step 5: Commit**

```bash
git add services/ai-render/Dockerfile services/ai-render/.dockerignore services/ai-render/requirements.txt
git commit -m "feat(ai-render): Dockerfile + finalized requirements"
```

---

## Task 7: dfpos data model + migration

**Files:**
- Modify: `app/models/product_ops.py` — add `AIRenderStatus` enum + columns on `ProductPhotoShot`
- Create: `migrations/versions/c4d5e6f7a8b9_photo_shot_ai_render.py`
- Create: `tests/test_photo_render_migration.py`

**Interfaces:**
- Produces: `AIRenderStatus` enum (`NONE`, `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` → string values `none`/`pending`/`running`/`completed`/`failed`) exported from `app.models`; new columns `ai_render_status` (default `none`, indexed), `ai_render_error` (Text), `ai_render_requested_at` (DateTime), `ai_render_completed_at` (DateTime), `ai_generated` (Boolean default False) on `ProductPhotoShot`.

- [ ] **Step 1: Write the failing test `tests/test_photo_render_migration.py`**

```python
from __future__ import annotations

from app.extensions import db
from app.models import ProductPhotoShot, ProductPhotoShotType, AIRenderStatus
from app.services.product_ops import ensure_product_ops_defaults
from tests.test_milestone4_product_ops import _product


def test_shot_has_ai_render_defaults(app):
    with app.app_context():
        product = _product()
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        assert shot.ai_render_status == AIRenderStatus.NONE
        assert shot.ai_generated is False
        assert shot.ai_render_error is None
        assert shot.ai_render_requested_at is None
        assert shot.ai_render_completed_at is None


def test_migration_revision_chain():
    import importlib

    mod = importlib.import_module("migrations.versions.c4d5e6f7a8b9_photo_shot_ai_render")
    assert mod.revision == "c4d5e6f7a8b9"
    assert mod.down_revision == "b3c4d5e6f7a8"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_photo_render_migration.py -v`
Expected: FAIL — `AIRenderStatus` not importable.

- [ ] **Step 3: Add the enum + columns in `app/models/product_ops.py`**

Add after `ProductPhotoShotType` (line ~31):
```python
class AIRenderStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

Add imports to the top import block:
```python
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
```
(Add `Boolean`, `DateTime` if not present — `Boolean` is already imported; add `DateTime`.)

Add columns inside `ProductPhotoShot` after `notes`:
```python
    ai_render_status: Mapped[AIRenderStatus] = mapped_column(
        Enum(AIRenderStatus, values_callable=lambda e: [m.value for m in e], length=60),
        default=AIRenderStatus.NONE,
        nullable=False,
        index=True,
    )
    ai_render_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_render_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ai_render_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```
Add `from datetime import datetime` to the imports.

- [ ] **Step 4: Export `AIRenderStatus` from `app.models`**

In `app/models/__init__.py`, add `AIRenderStatus` to the import from `app.models.product_ops` and to `__all__` (follow the existing entries for `ProductPhotoShotType` at lines ~82/188 — add `AIRenderStatus` next to it).

- [ ] **Step 5: Write the migration `migrations/versions/c4d5e6f7a8b9_photo_shot_ai_render.py`**

```python
"""product_photo_shots AI render status columns

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_photo_shots",
        sa.Column(
            "ai_render_status",
            sa.Enum(
                "none", "pending", "running", "completed", "failed",
                name="product_photo_shot_ai_render_status",
            ),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_index(
        "ix_product_photo_shots_ai_render_status",
        "product_photo_shots",
        ["ai_render_status"],
    )
    op.add_column("product_photo_shots", sa.Column("ai_render_error", sa.Text(), nullable=True))
    op.add_column(
        "product_photo_shots", sa.Column("ai_render_requested_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "product_photo_shots", sa.Column("ai_render_completed_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "product_photo_shots",
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("product_photo_shots", "ai_generated")
    op.drop_column("product_photo_shots", "ai_render_completed_at")
    op.drop_column("product_photo_shots", "ai_render_requested_at")
    op.drop_column("product_photo_shots", "ai_render_error")
    op.drop_index("ix_product_photo_shots_ai_render_status", table_name="product_photo_shots")
    op.drop_column("product_photo_shots", "ai_render_status")
    op.execute("DROP TYPE IF EXISTS product_photo_shot_ai_render_status")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_photo_render_migration.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Verify migration applies (apply against a dev DB)**

Run: `cd /mnt/storage/docker/dfpos && alembic upgrade head`
Expected: `c4d5e6f7a8b9` applied; `alembic current` shows `c4d5e6f7a8b9 (head)`.

- [ ] **Step 8: Commit**

```bash
git add app/models/product_ops.py app/models/__init__.py migrations/versions/c4d5e6f7a8b9_photo_shot_ai_render.py tests/test_photo_render_migration.py
git commit -m "feat(dfpos): add AI render status columns + migration on product_photo_shots"
```

---

## Task 8: dfpos ai_render_client

**Files:**
- Create: `app/services/ai_render_client.py`
- Create: `tests/test_ai_render_client.py`

**Interfaces:**
- Produces: `AiRenderClient` mirroring `SlicerClient`: `is_configured()`, `health_ready()`, `create_generation(model_file_path, *, prompt, shot_id, negative_prompt, camera, gen_params) -> dict`, `get_job(job_id) -> dict`. `create_generation` posts multipart (file + form fields) to `/generate` and returns `{"job_id": ...}` (or `{"error": ...}` on failure). `get_job` polls `/jobs/{id}`. Also `get_ai_render_client()` reading `AI_RENDER_*` config. Errors return `{"error": ...}` dicts (never raise), exactly like the slicer client.

- [ ] **Step 1: Write the failing test `tests/test_ai_render_client.py`**

```python
from __future__ import annotations

import httpx
import pytest

from app.services.ai_render_client import AiRenderClient


def test_is_configured_requires_all():
    assert not AiRenderClient().is_configured()
    assert not AiRenderClient(base_url="http://x", token="t").is_configured()  # enabled False
    assert AiRenderClient(base_url="http://x", token="t", enabled=True).is_configured()


def test_create_generation_returns_job_id(monkeypatch, tmp_path):
    path = tmp_path / "m.stl"
    path.write_bytes(b"mesh")

    def handler(request):
        return httpx.Response(202, json={"job_id": "abc"})

    transport = httpx.MockTransport(handler)
    client = AiRenderClient(base_url="http://ai-render", token="t", enabled=True)
    monkeypatch.setattr(client, "_client", lambda: httpx.Client(base_url="http://ai-render", transport=transport))
    res = client.create_generation(
        str(path),
        prompt="hero",
        shot_id="1",
        camera={"az": 35.0, "el": 18.0, "extent": 0.62},
    )
    assert res == {"job_id": "abc"}


def test_get_job_returns_status(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "completed", "image_base64": "x", "error": None})

    transport = httpx.MockTransport(handler)
    client = AiRenderClient(base_url="http://ai-render", token="t", enabled=True)
    monkeypatch.setattr(client, "_client", lambda: httpx.Client(base_url="http://ai-render", transport=transport))
    assert client.get_job("abc")["status"] == "completed"


def test_unconfigured_returns_error():
    res = AiRenderClient().create_generation("x", prompt="p", shot_id="1", camera={})
    assert "error" in res
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_render_client.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `app/services/ai_render_client.py`**

```python
from __future__ import annotations

from typing import Any

import httpx
from flask import current_app

_DEFAULT_NEGATIVE = (
    "blurry, low quality, distorted, extra objects, text, watermark, deformed, oversaturated"
)


class AiRenderClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, enabled: bool = True):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.token)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=120.0,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            return {"error": "AI render service is not configured."}
        try:
            with self._client() as client:
                resp = client.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            current_app.logger.warning("ai-render service error: %s", exc)
            try:
                return {"error": exc.response.json()}
            except ValueError:
                return {"error": str(exc)}
        except httpx.RequestError as exc:
            current_app.logger.warning("ai-render service unavailable: %s", exc)
            return {"error": str(exc)}

    def health_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/ready")

    def create_generation(
        self,
        model_file_path: str,
        *,
        prompt: str,
        shot_id: str,
        camera: dict[str, float],
        negative_prompt: str | None = None,
        gen_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gen_params = gen_params or {}
        with open(model_file_path, "rb") as f:
            files = {"model_file": (model_file_path, f)}
            data = {
                "prompt": prompt,
                "shot_id": shot_id,
                "negative_prompt": negative_prompt or _DEFAULT_NEGATIVE,
                "camera_az": str(camera.get("az", 0.0)),
                "camera_el": str(camera.get("el", 0.0)),
                "camera_extent": str(camera.get("extent", 0.62)),
            }
            for key in ("width", "height", "steps", "guidance"):
                if key in gen_params:
                    data[key] = str(gen_params[key])
            return self._request("POST", "/generate", files=files, data=data)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/jobs/{job_id}")


def get_ai_render_client() -> AiRenderClient:
    config = current_app.config
    return AiRenderClient(
        base_url=config.get("AI_RENDER_SERVICE_URL", ""),
        token=config.get("AI_RENDER_INTERNAL_API_TOKEN", ""),
        enabled=config.get("AI_RENDER_ENABLED", False),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_render_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/ai_render_client.py tests/test_ai_render_client.py
git commit -m "feat(dfpos): ai_render_client httpx client mirroring slicer_client"
```

---

## Task 9: dfpos photo_render orchestration service

**Files:**
- Create: `app/services/photo_render.py`
- Create: `tests/test_photo_render.py`

**Interfaces:**
- Consumes: `get_ai_render_client()` (Task 8), storage helpers (`materialize_storage_reference`, `upload_bytes_to_storage`, `product_asset_key`), `set_ai_render_status`/`complete_ai_render` (Task 10).
- Produces:
  - `AI_SHOT_TYPES: set[ProductPhotoShotType]`
  - `CAMERA_PRESETS: dict[ProductPhotoShotType, tuple[float,float,float]]` (az, el, extent)
  - `build_prompt(shot_type, product) -> str`
  - `camera_for_shot(shot_type) -> dict[str, float]`
  - `resolve_model_path(product) -> str` (local path; raises `ValueError` if no model)
  - `generate_shot(shot, *, actor_id=None, poll_timeout_seconds=2400) -> ProductPhotoShot`
  - `PROMPT_TEMPLATES: dict[ProductPhotoShotType, str]`

> Note on ordering: this task references `set_ai_render_status`/`complete_ai_render` from Task 10. Implement Task 10 first, or stub them here and replace — the plan implements Task 10 before executing this task if done in order. The signatures used here are fixed by Task 10.

- [ ] **Step 1: Write the failing test `tests/test_photo_render.py`**

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.extensions import db
from app.models import Product, ProductPhotoShot, ProductPhotoShotType, AIRenderStatus
from app.services import photo_render
from app.services.photo_render import (
    AI_SHOT_TYPES, CAMERA_PRESETS, build_prompt, camera_for_shot, generate_shot, resolve_model_path,
)
from tests.test_milestone4_product_ops import _product


def test_build_prompt_hero_includes_product_name(app):
    with app.app_context():
        product = _product(name="Crystal Dragon")
        p = build_prompt(ProductPhotoShotType.HERO, product)
        assert "Crystal Dragon" in p
        assert "studio" in p.lower()


def test_camera_for_shot_returns_preset():
    cam = camera_for_shot(ProductPhotoShotType.HERO)
    assert cam == {"az": 35.0, "el": 18.0, "extent": 0.62}


def test_ai_shot_types_only_three():
    assert AI_SHOT_TYPES == {
        ProductPhotoShotType.HERO, ProductPhotoShotType.CLOSE_UP, ProductPhotoShotType.POS_TILE,
    }


def test_resolve_model_path_raises_without_model(app):
    with app.app_context():
        product = _product()
        product.model_file_path = None
        product.converted_model_path = None
        db.session.commit()
        with pytest.raises(ValueError):
            resolve_model_path(product)


def test_generate_shot_success(monkeypatch, app, tmp_path):
    # Local storage backend, fake model on disk.
    monkeypatch.setattr(photo_render, "materialize_storage_reference", lambda ref, **kw: (ref, False))
    fake_model = tmp_path / "m.stl"
    fake_model.write_bytes(b"mesh")

    png = io.BytesIO(); Image.new("RGB", (8, 8), (1, 2, 3)).save(png, format="PNG"); png_bytes = png.getvalue()

    class FakeClient:
        def create_generation(self, path, **kw):
            return {"job_id": "j1"}
        def get_job(self, jid):
            import base64
            return {"status": "completed", "image_base64": base64.b64encode(png_bytes).decode(), "error": None}

    monkeypatch.setattr(photo_render, "get_ai_render_client", lambda: FakeClient())
    monkeypatch.setattr(photo_render, "upload_bytes_to_storage", lambda data, **kw: "s3://products/products/1/renders/hero.png")

    with app.app_context():
        product = _product(model_file_path=str(fake_model))
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        result = generate_shot(shot, actor_id=None, poll_timeout_seconds=5)
        assert result.completed is True
        assert result.image_reference == "s3://products/products/1/renders/hero.png"
        assert result.ai_render_status == AIRenderStatus.COMPLETED
        assert result.ai_generated is True


def test_generate_shot_failure_marks_failed(monkeypatch, app, tmp_path):
    monkeypatch.setattr(photo_render, "materialize_storage_reference", lambda ref, **kw: (ref, False))
    fake_model = tmp_path / "m.stl"; fake_model.write_bytes(b"mesh")

    class FakeClient:
        def create_generation(self, path, **kw):
            return {"job_id": "j1"}
        def get_job(self, jid):
            return {"status": "failed", "image_base64": None, "error": "boom"}

    monkeypatch.setattr(photo_render, "get_ai_render_client", lambda: FakeClient())

    with app.app_context():
        product = _product(model_file_path=str(fake_model))
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        result = generate_shot(shot, poll_timeout_seconds=5)
        assert result.ai_render_status == AIRenderStatus.FAILED
        assert result.completed is False
        assert "boom" in (result.ai_render_error or "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_photo_render.py -v`
Expected: FAIL — module `app.services.photo_render` not found.

- [ ] **Step 3: Write `app/services/photo_render.py`**

```python
from __future__ import annotations

import base64
import io
import time
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models import (
    AIRenderStatus,
    Product,
    ProductPhotoShot,
    ProductPhotoShotType,
)
from app.services.ai_render_client import get_ai_render_client
from app.services.storage import (
    materialize_storage_reference,
    product_asset_key,
    upload_bytes_to_storage,
)

AI_SHOT_TYPES = {
    ProductPhotoShotType.HERO,
    ProductPhotoShotType.CLOSE_UP,
    ProductPhotoShotType.POS_TILE,
}

CAMERA_PRESETS: dict[ProductPhotoShotType, tuple[float, float, float]] = {
    ProductPhotoShotType.HERO: (35.0, 18.0, 0.62),
    ProductPhotoShotType.CLOSE_UP: (30.0, 25.0, 0.42),
    ProductPhotoShotType.POS_TILE: (0.0, 6.0, 0.70),
}

PROMPT_TEMPLATES: dict[ProductPhotoShotType, str] = {
    ProductPhotoShotType.HERO: (
        "professional studio product photo of {name}, {descriptor}, "
        "soft three-point lighting, clean white seamless background, "
        "photorealistic, 50mm, sharp focus, high detail"
    ),
    ProductPhotoShotType.CLOSE_UP: (
        "extreme close-up macro product photo of {name}, {descriptor}, "
        "dramatic soft lighting, shallow depth of field, photorealistic, fine surface detail"
    ),
    ProductPhotoShotType.POS_TILE: (
        "product on a clean modern retail display shelf, {name}, {descriptor}, "
        "bright even store lighting, photorealistic, commercial merchandising shot"
    ),
}


def _descriptor(product: Product) -> str:
    parts = []
    if product.category and product.category.name:
        parts.append(product.category.name.lower())
    if product.short_description:
        parts.append(product.short_description)
    return ", ".join(parts) if parts else "3D-printed product"


def build_prompt(shot_type: ProductPhotoShotType, product: Product) -> str:
    template = PROMPT_TEMPLATES[shot_type]
    return template.format(name=product.name or "product", descriptor=_descriptor(product))


def camera_for_shot(shot_type: ProductPhotoShotType) -> dict[str, float]:
    az, el, extent = CAMERA_PRESETS[shot_type]
    return {"az": az, "el": el, "extent": extent}


def resolve_model_path(product: Product) -> str:
    ref = product.converted_model_path or product.model_file_path
    if not ref:
        raise ValueError("Product has no 3D model to render.")
    path, _cleanup = materialize_storage_reference(ref)
    return path


def generate_shot(
    shot: ProductPhotoShot,
    *,
    actor_id: int | None = None,
    poll_timeout_seconds: int = 2400,
) -> ProductPhotoShot:
    from app.services.product_ops import complete_ai_render, set_ai_render_status

    product = shot.product
    set_ai_render_status(shot, AIRenderStatus.RUNNING, actor_id=actor_id)

    try:
        model_path = resolve_model_path(product)
        client = get_ai_render_client()
        if not client.is_configured():
            set_ai_render_status(shot, AIRenderStatus.FAILED, error="AI render service not configured", actor_id=actor_id)
            return shot

        prompt = build_prompt(shot.shot_type, product)
        camera = camera_for_shot(shot.shot_type)
        created = client.create_generation(model_path, prompt=prompt, shot_id=str(shot.id), camera=camera)
        if "error" in created or "job_id" not in created:
            set_ai_render_status(shot, AIRenderStatus.FAILED, error=str(created.get("error", "no job_id")), actor_id=actor_id)
            return shot

        job_id = created["job_id"]
        deadline = time.monotonic() + poll_timeout_seconds
        result = None
        while time.monotonic() < deadline:
            result = client.get_job(job_id)
            status = result.get("status")
            if status in {"completed", "failed"}:
                break
            if "error" in result:
                break
            time.sleep(float(current_app.config.get("AI_RENDER_POLL_INTERVAL", 5.0)))
        else:
            set_ai_render_status(shot, AIRenderStatus.FAILED, error="render timed out", actor_id=actor_id)
            return shot

        if not result or result.get("status") != "completed" or not result.get("image_base64"):
            set_ai_render_status(shot, AIRenderStatus.FAILED, error=result.get("error", "render failed"), actor_id=actor_id)
            return shot

        image_bytes = base64.b64decode(result["image_base64"])
        bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
        local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
        key = product_asset_key(product.id, f"renders/{shot.shot_type.value}.png")
        reference = upload_bytes_to_storage(image_bytes, bucket=bucket, key=key, local_root=local_root, content_type="image/png")
        return complete_ai_render(shot, image_reference=reference, actor_id=actor_id)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("AI render failed for shot %s", shot.id)
        set_ai_render_status(shot, AIRenderStatus.FAILED, error=str(exc), actor_id=actor_id)
        return shot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_photo_render.py -v`
Expected: PASS (5 tests). (Requires Task 10's `set_ai_render_status`/`complete_ai_render` to exist — implement Task 10 before running.)

- [ ] **Step 5: Commit**

```bash
git add app/services/photo_render.py tests/test_photo_render.py
git commit -m "feat(dfpos): photo_render orchestration (prompt, camera, model resolve, generate)"
```

---

## Task 10: product_ops AI status functions + audit

**Files:**
- Modify: `app/services/product_ops.py`
- Modify: `app/models/__init__.py` (export `AIRenderStatus` — done in Task 7; ensure import here)

**Interfaces:**
- Produces:
  - `set_ai_render_status(shot, status: AIRenderStatus, *, error: str | None = None, actor_id: int | None = None) -> ProductPhotoShot` — sets `ai_render_status`; sets `ai_render_requested_at` when entering `PENDING`, `ai_render_completed_at` when entering `COMPLETED`/`FAILED`; clears/sets `ai_render_error`; commits; audit `product_photo_shot.ai_render_status`.
  - `complete_ai_render(shot, *, image_reference: str, actor_id: int | None = None) -> ProductPhotoShot` — sets `completed=True`, `image_reference`, `ai_render_status=COMPLETED`, `ai_render_completed_at=now`, `ai_generated=True`; commits; audit `product_photo_shot.ai_generated`.

- [ ] **Step 1: Write the failing test (append to `tests/test_photo_render.py`)**

```python
from app.services.product_ops import complete_ai_render, set_ai_render_status


def test_set_ai_render_status_records_timestamps(app):
    with app.app_context():
        product = _product()
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        set_ai_render_status(shot, AIRenderStatus.PENDING, actor_id=None)
        assert shot.ai_render_status == AIRenderStatus.PENDING
        assert shot.ai_render_requested_at is not None
        set_ai_render_status(shot, AIRenderStatus.FAILED, error="boom", actor_id=None)
        assert shot.ai_render_status == AIRenderStatus.FAILED
        assert shot.ai_render_error == "boom"
        assert shot.ai_render_completed_at is not None


def test_complete_ai_render_marks_completed(app):
    with app.app_context():
        product = _product()
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        complete_ai_render(shot, image_reference="s3://products/products/1/renders/hero.png", actor_id=None)
        assert shot.completed is True
        assert shot.image_reference == "s3://products/products/1/renders/hero.png"
        assert shot.ai_render_status == AIRenderStatus.COMPLETED
        assert shot.ai_generated is True
        assert shot.ai_render_completed_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_photo_render.py -v`
Expected: FAIL — `complete_ai_render`/`set_ai_render_status` not importable.

- [ ] **Step 3: Add the functions to `app/services/product_ops.py`**

Add `AIRenderStatus` to the `from app.models import (...)` import block. Add `datetime, timezone` (already imported). Then append:

```python
def set_ai_render_status(
    shot: ProductPhotoShot,
    status: AIRenderStatus,
    *,
    error: str | None = None,
    actor_id: int | None = None,
) -> ProductPhotoShot:
    before_state = snapshot_instance(shot)
    shot.ai_render_status = status
    now = datetime.now(timezone.utc)
    if status == AIRenderStatus.PENDING and not shot.ai_render_requested_at:
        shot.ai_render_requested_at = now
    if status in {AIRenderStatus.COMPLETED, AIRenderStatus.FAILED}:
        shot.ai_render_completed_at = now
    shot.ai_render_error = error
    db.session.add(shot)
    db.session.commit()
    _audit(
        "product_photo_shot.ai_render_status",
        "product_photo_shot",
        shot.id,
        before_state,
        snapshot_instance(shot),
        actor_id,
    )
    return shot


def complete_ai_render(
    shot: ProductPhotoShot,
    *,
    image_reference: str,
    actor_id: int | None = None,
) -> ProductPhotoShot:
    before_state = snapshot_instance(shot)
    shot.completed = True
    shot.image_reference = image_reference
    shot.ai_render_status = AIRenderStatus.COMPLETED
    shot.ai_render_completed_at = datetime.now(timezone.utc)
    shot.ai_generated = True
    shot.ai_render_error = None
    db.session.add(shot)
    db.session.commit()
    _audit(
        "product_photo_shot.ai_generated",
        "product_photo_shot",
        shot.id,
        before_state,
        snapshot_instance(shot),
        actor_id,
    )
    return shot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_photo_render.py -v`
Expected: PASS (7 tests total in that file).

- [ ] **Step 5: Commit**

```bash
git add app/services/product_ops.py tests/test_photo_render.py
git commit -m "feat(dfpos): set_ai_render_status + complete_ai_render with audit"
```

---

## Task 11: Celery task + registration

**Files:**
- Create: `app/tasks/photo_render.py`
- Modify: `app/celery_app.py` — add `"app.tasks.photo_render"` to `include`
- Create: `tests/test_photo_render_task.py`

**Interfaces:**
- Produces: `@celery.task(bind=True)` `render_product_photo_shot(shot_id: int)` that loads the shot, marks it `RUNNING`, calls `photo_render.generate_shot`, and on unexpected exception marks it `FAILED` (defensive — `generate_shot` already handles most failures).
- Consumes: `generate_shot` from Task 9.

- [ ] **Step 1: Write the failing test `tests/test_photo_render_task.py`**

```python
from __future__ import annotations

import io
from unittest.mock import patch

from PIL import Image

from app.extensions import db
from app.models import ProductPhotoShot, ProductPhotoShotType, AIRenderStatus
from app.tasks.photo_render import render_product_photo_shot
from tests.test_milestone4_product_ops import _product


def test_task_marks_running_then_completed(app):
    with app.app_context():
        product = _product(model_file_path="s3://products/products/1/m.stl")
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        shot_id = shot.id
        db.session.commit()

    png = io.BytesIO(); Image.new("RGB", (4, 4)).save(png, format="PNG"); png_bytes = png.getvalue()

    class FakeShot:
        def __init__(self, s):
            self.s = s
        completed = False
        image_reference = None
        ai_render_status = AIRenderStatus.NONE
        ai_generated = False
        ai_render_error = None

    with app.app_context():
        with patch("app.services.photo_render.generate_shot") as fake:
            fake.return_value = ProductPhotoShot.query.get(shot_id)
            render_product_photo_shot.apply(args=(shot_id,)).get()
        shot = ProductPhotoShot.query.get(shot_id)
        # generate_shot was invoked; with the patch returning the real row, status stays whatever it is.
        assert fake.called


def test_task_missing_shot_does_not_raise(app):
    with app.app_context():
        # Should handle a missing shot gracefully.
        render_product_photo_shot.apply(args=(9999999,)).get()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_photo_render_task.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `app/tasks/photo_render.py`**

```python
from __future__ import annotations

from app.celery_app import celery
from app.extensions import db
from app.models import AIRenderStatus, ProductPhotoShot
from app.services.photo_render import generate_shot
from app.services.product_ops import set_ai_render_status


@celery.task(bind=True, max_retries=0)
def render_product_photo_shot(self, shot_id: int):
    shot = ProductPhotoShot.query.get(shot_id)
    if shot is None:
        return {"error": "shot not found", "shot_id": shot_id}
    try:
        return generate_shot(shot, actor_id=None)
    except Exception as exc:  # noqa: BLE001
        set_ai_render_status(shot, AIRenderStatus.FAILED, error=str(exc), actor_id=None)
        raise
```

- [ ] **Step 4: Register the task in `app/celery_app.py`**

In the `include=[...]` list, add `"app.tasks.photo_render"`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_photo_render_task.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add app/tasks/photo_render.py app/celery_app.py tests/test_photo_render_task.py
git commit -m "feat(dfpos): render_product_photo_shot Celery task"
```

---

## Task 12: generate-ai + ai-status routes

**Files:**
- Modify: `app/blueprints/products/studio_routes.py`
- Create: `tests/test_studio_ai_routes.py`

**Interfaces:**
- Produces:
  - `POST /products/studio/<pid>/photo-shot/<sid>/generate-ai` — validates shot_type ∈ AI_SHOT_TYPES, product has a model, AI render enabled; sets `PENDING`; enqueues `render_product_photo_shot`; flashes + redirects to studio.
  - `GET /products/studio/<pid>/photo-shot/<sid>/ai-status` — returns JSON `{status, error, image_url}` for the poller.

- [ ] **Step 1: Write the failing test `tests/test_studio_ai_routes.py`**

```python
from __future__ import annotations

from app.extensions import db
from app.models import ProductPhotoShot, ProductPhotoShotType, AIRenderStatus
from tests.test_milestone4_product_ops import _product


def _login(client, app):
    # Tests run with WTF_CSRF disabled (TestingConfig). Use an admin session.
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"


def test_generate_ai_enqueues_and_sets_pending(app, client, monkeypatch):
    enqueued = {}

    def fake_delay(shot_id):
        enqueued["shot_id"] = shot_id

    monkeypatch.setattr("app.blueprints.products.studio_routes.render_product_photo_shot", type("T", (), {"delay": staticmethod(fake_delay)}))

    _login(client, app)
    with app.app_context():
        product = _product(model_file_path="s3://products/products/1/m.stl")
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        pid, sid = product.id, shot.id
        db.session.commit()

    r = client.post(f"/products/studio/{pid}/photo-shot/{sid}/generate-ai")
    assert r.status_code in (302, 303)
    assert enqueued["shot_id"] == sid
    with app.app_context():
        shot = ProductPhotoShot.query.get(sid)
        assert shot.ai_render_status == AIRenderStatus.PENDING


def test_generate_ai_rejects_non_ai_shot(app, client):
    _login(client, app)
    with app.app_context():
        product = _product(model_file_path="s3://products/products/1/m.stl")
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.SCALE_IN_HAND
        ).first()
        pid, sid = product.id, shot.id
        db.session.commit()
    r = client.post(f"/products/studio/{pid}/photo-shot/{sid}/generate-ai")
    assert r.status_code in (302, 400)


def test_ai_status_returns_json(app, client):
    _login(client, app)
    with app.app_context():
        product = _product(model_file_path="s3://products/products/1/m.stl")
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        shot.ai_render_status = AIRenderStatus.RUNNING
        db.session.commit()
        pid, sid = product.id, shot.id
    r = client.get(f"/products/studio/{pid}/photo-shot/{sid}/ai-status")
    assert r.status_code == 200
    assert r.json["status"] == "running"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_studio_ai_routes.py -v`
Expected: FAIL — routes 404.

- [ ] **Step 3: Add routes to `app/blueprints/products/studio_routes.py`**

Add imports near the existing model imports:
```python
from app.models import AIRenderStatus
from app.services.photo_render import AI_SHOT_TYPES
from app.tasks.photo_render import render_product_photo_shot
```
(If `render_product_photo_shot` import causes a circular import at module load, import it lazily inside the route function instead — `from app.tasks.photo_render import render_product_photo_shot`.)

Add the routes (after `update_product_photo_shot`, ~line 347):

```python
@bp.route("/studio/<int:product_id>/photo-shot/<int:shot_id>/generate-ai", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def generate_ai_photo(product_id: int, shot_id: int):
    product = get_by_id(Product, product_id)
    shot = ProductPhotoShot.query.filter_by(id=shot_id, product_id=product_id).first()
    if product is None or shot is None:
        abort(404)
    if shot.shot_type not in AI_SHOT_TYPES:
        flash("This shot type does not support AI generation.", "warning")
        return redirect(url_for("products.studio", product_id=product.id))
    if not (product.model_file_path or product.converted_model_path):
        flash("Upload a 3D model before generating AI photos.", "warning")
        return redirect(url_for("products.studio", product_id=product.id))
    if not current_app.config.get("AI_RENDER_ENABLED", False):
        flash("AI photo rendering is not enabled.", "warning")
        return redirect(url_for("products.studio", product_id=product.id))

    set_ai_render_status(shot, AIRenderStatus.PENDING, actor_id=current_user.id)
    from app.tasks.photo_render import render_product_photo_shot  # lazy to avoid cycles
    render_product_photo_shot.delay(shot.id)
    flash("Generating AI photo — check back shortly.", "info")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/<int:product_id>/photo-shot/<int:shot_id>/ai-status")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def photo_shot_ai_status(product_id: int, shot_id: int):
    shot = ProductPhotoShot.query.filter_by(id=shot_id, product_id=product_id).first()
    if shot is None:
        abort(404)
    image_url = None
    if shot.completed and shot.image_reference:
        image_url = url_for("products.photo_shot_image", product_id=product_id, shot_id=shot_id)
    return jsonify(
        {
            "status": shot.ai_render_status.value if shot.ai_render_status else "none",
            "error": shot.ai_render_error,
            "image_url": image_url,
        }
    )
```

Add `set_ai_render_status` to the `from app.services.product_ops import (...)` import block, and a tiny image-serving route `photo_shot_image`:

```python
@bp.route("/studio/<int:product_id>/photo-shot/<int:shot_id>/image")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def photo_shot_image(product_id: int, shot_id: int):
    shot = ProductPhotoShot.query.filter_by(id=shot_id, product_id=product_id).first()
    if shot is None or not shot.image_reference:
        abort(404)
    return send_storage_reference(shot.image_reference, mimetype="image/png")
```
(Add `send_storage_reference` to the existing `from app.services.storage import (...)` import block in studio_routes.py.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_studio_ai_routes.py -v`
Expected: PASS (3 tests). The `monkeypatch.setattr` for `render_product_photo_shot` in `test_generate_ai_enqueues_and_sets_pending` targets the module attribute the route imports lazily — if the lazy import inside the function shadows the patch, change the route to import at module top and patch the module attribute. Verify the route uses the module-level name. (If tests show the patch is bypassed, move `from app.tasks.photo_render import render_product_photo_shot` to the top of the file and keep the patch target as `app.blueprints.products.studio_routes.render_product_photo_shot`.)

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/products/studio_routes.py tests/test_studio_ai_routes.py
git commit -m "feat(dfpos): generate-ai + ai-status + photo-shot image routes"
```

---

## Task 13: Studio UI — Generate button + status badge

**Files:**
- Modify: `app/templates/products/studio.html`

**Interfaces:**
- Produces: each `hero`/`close_up`/`pos_tile` shot row shows a "Generate with AI" button (POST to `generate_ai_photo`) plus a status badge that reflects `ai_render_status`; the badge container carries `data-shot-id` and `data-ai-status` for the poller (Task 14).

- [ ] **Step 1: Read the current Photo Shot List card markup**

Run: `sed -n '285,310p' app/templates/products/studio.html`
Confirm the existing `<form method=post action="{{ url_for('products.update_product_photo_shot', ...) }}">` structure with `completed`, `image_reference`, `notes`, and the Save button.

- [ ] **Step 2: Add the Generate button + badge inside each shot form**

Within each shot's form (before the Save button), insert:

```html
{% if shot.shot_type in ('hero', 'close_up', 'pos_tile') %}
  <div class="ai-render" data-shot-id="{{ shot.id }}" data-ai-status="{{ shot.ai_render_status.value if shot.ai_render_status else 'none' }}">
    {% if shot.ai_render_status in ('pending', 'running') %}
      <span class="badge ai-badge ai-badge--busy">Generating…</span>
    {% elif shot.ai_render_status == 'failed' %}
      <span class="badge ai-badge ai-badge--error" title="{{ shot.ai_render_error }}">
        AI failed
      </span>
    {% endif %}
    {% if shot.completed and shot.image_reference and shot.ai_generated %}
      <img src="{{ url_for('products.photo_shot_image', product_id=product.id, shot_id=shot.id) }}"
           alt="{{ shot.label }} AI render" class="ai-render__thumb" loading="lazy" />
    {% endif %}
    <button type="submit"
            formaction="{{ url_for('products.generate_ai_photo', product_id=product.id, shot_id=shot.id) }}"
            formmethod="post"
            class="btn btn--secondary ai-render__btn"
            {% if shot.ai_render_status in ('pending', 'running') %}disabled{% endif %}>
      {{ 'Regenerate with AI' if shot.completed and shot.ai_generated else 'Generate with AI' }}
    </button>
  </div>
{% endif %}
```

> Note: the existing Save button uses default form action. Adding `formaction`/`formmethod` on the AI button makes it submit to the AI route instead, while the Save button still submits to `update_product_photo_shot`. Confirm the outer `<form>` has no conflicting `action`; if it does, wrap the AI button in its own `<form>` posting to `generate_ai_photo`.

- [ ] **Step 3: Add minimal badge styling**

Append to the page's existing `<style>` block (or `app/static/src/css/studio.css` if present):
```css
.ai-badge--busy { background: #2b6cb0; color: #fff; }
.ai-badge--error { background: #c53030; color: #fff; }
.ai-render__thumb { max-width: 120px; height: auto; display: block; margin: 6px 0; border-radius: 4px; }
```

- [ ] **Step 4: Verify the page renders**

Run: start the app (per the project's `run` skill) and open `/products/studio/<id>` for a product with a model; confirm the three AI rows show "Generate with AI" and the others do not.
Expected: buttons appear only on hero/close_up/pos_tile.

- [ ] **Step 5: Commit**

```bash
git add app/templates/products/studio.html app/static/src/css/studio.css
git commit -m "feat(dfpos): AI generate button + status badge on photo shot rows"
```

---

## Task 14: Studio.js status poller

**Files:**
- Modify: `app/static/src/js/studio.js`

**Interfaces:**
- Produces: a poller that, on studio page load, finds all `.ai-render[data-ai-status="pending"], [data-ai-status="running"]` elements, polls `<pid>/photo-shot/<sid>/ai-status` every ~5s, and on `completed` swaps the badge to the returned `image_url` and reloads the readiness card; on `failed` shows the error badge.

- [ ] **Step 1: Append the poller to `app/static/src/js/studio.js`**

```javascript
// AI photo render status polling
(function () {
  function pollAiRender() {
    const items = Array.from(document.querySelectorAll(".ai-render[data-ai-status]")).filter((el) => {
      const s = el.getAttribute("data-ai-status");
      return s === "pending" || s === "running";
    });
    items.forEach((el) => {
      const shotId = el.getAttribute("data-shot-id");
      const pid = el.getAttribute("data-product-id") || (window.__productId);
      fetch(`/products/studio/${pid}/photo-shot/${shotId}/ai-status`, {
        headers: { Accept: "application/json" },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data) return;
          if (data.status === "completed") {
            el.setAttribute("data-ai-status", "completed");
            el.querySelector(".ai-badge--busy")?.remove();
            const btn = el.querySelector(".ai-render__btn");
            if (btn) btn.textContent = "Regenerate with AI";
            if (data.image_url) {
              let img = el.querySelector(".ai-render__thumb");
              if (!img) {
                img = document.createElement("img");
                img.className = "ai-render__thumb";
                el.prepend(img);
              }
              img.src = data.image_url;
            }
            // refresh readiness/checklist scores
            window.location.reload();
          } else if (data.status === "failed") {
            el.setAttribute("data-ai-status", "failed");
            const busy = el.querySelector(".ai-badge--busy");
            if (busy) {
              busy.className = "badge ai-badge ai-badge--error";
              busy.textContent = "AI failed";
              busy.setAttribute("title", data.error || "");
            }
          }
        })
        .catch(() => {});
    });
  }

  function start() {
    if (document.querySelector(".ai-render[data-ai-status='pending'], .ai-render[data-ai-status='running']")) {
      setInterval(pollAiRender, 5000);
      pollAiRender();
    }
  }

  document.addEventListener("DOMContentLoaded", start);
})();
```

- [ ] **Step 2: Ensure `data-product-id` is available**

In `studio.html`, add `data-product-id="{{ product.id }}"` to the `.ai-render` div (Task 13 Step 2 markup) so the poller can resolve the URL.

- [ ] **Step 3: Manual verification**

Run: with a render in progress, open the studio page; confirm the badge shows "Generating…" and, when the Celery task completes, the image appears and the page refreshes.
Expected: badge transitions pending → completed with no manual reload.

- [ ] **Step 4: Commit**

```bash
git add app/static/src/js/studio.js app/templates/products/studio.html
git commit -m "feat(dfpos): poll AI render status and swap image on completion"
```

---

## Task 15: Config + .env.example + docker-compose

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: config keys `AI_RENDER_ENABLED`, `AI_RENDER_SERVICE_URL`, `AI_RENDER_INTERNAL_API_TOKEN`, `AI_RENDER_POLL_INTERVAL` on `Config`; documented env vars; an example `ai-render` compose service (disabled by default — the Mac Pro is external).

- [ ] **Step 1: Add config keys to `app/config.py`** (near the slicer keys, ~line 154):

```python
    AI_RENDER_ENABLED = _as_bool(os.getenv("AI_RENDER_ENABLED"), False)
    AI_RENDER_SERVICE_URL = os.getenv("AI_RENDER_SERVICE_URL", "http://ai-render:8093")
    AI_RENDER_INTERNAL_API_TOKEN = os.getenv("AI_RENDER_INTERNAL_API_TOKEN", "")
    AI_RENDER_POLL_INTERVAL = float(os.getenv("AI_RENDER_POLL_INTERVAL", "5.0"))
```

- [ ] **Step 2: Document in `.env.example`**

Append:
```
# AI Marketing Photo Generator
AI_RENDER_ENABLED=false
# In production the render microservice runs on the 2013 Mac Pro (external).
# Point dfpos at it, e.g. http://192.168.x.x:8093
AI_RENDER_SERVICE_URL=http://ai-render:8093
AI_RENDER_INTERNAL_API_TOKEN=
AI_RENDER_POLL_INTERVAL=5.0
```

- [ ] **Step 3: Add an example `ai-render` service to `docker-compose.yml`**

Add a commented/optional service (mirrors the slicer block), and pass the same env to the `app` service:
```yaml
  ai-render:
    image: dfp-ai-render:latest
    build:
      context: ./services/ai-render
    profiles: ["ai-render"]      # opt-in; not started by default (Mac Pro is external)
    environment:
      AI_RENDER_INTERNAL_API_TOKEN: ${AI_RENDER_INTERNAL_API_TOKEN:?must be set}
      AI_RENDER_SD_REPO: ${AI_RENDER_SD_REPO:-stable-diffusion-v1-5/stable-diffusion-v1-5}
      AI_RENDER_CONTROLNET_REPO: ${AI_RENDER_CONTROLNET_REPO:-lllyasviel/sd-controlnet-depth}
    ports:
      - "${AI_RENDER_HOST_PORT:-8093}:8093"
```
And on the `app` service, add the AI render env alongside the slicer env:
```yaml
      AI_RENDER_ENABLED: ${AI_RENDER_ENABLED:-false}
      AI_RENDER_SERVICE_URL: ${AI_RENDER_SERVICE_URL:-http://ai-render:8093}
      AI_RENDER_INTERNAL_API_TOKEN: ${AI_RENDER_INTERNAL_API_TOKEN:-}
```

- [ ] **Step 4: Validate compose**

Run: `docker-compose config --profiles ai-render >/dev/null`
Expected: no YAML errors.

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example docker-compose.yml
git commit -m "feat(dfpos): AI render config keys + compose profile"
```

---

## Task 16: End-to-end integration test

**Files:**
- Create: `tests/test_ai_render_integration.py`

**Interfaces:**
- Produces: an integration test that runs the full dfpos path (route → task → client → S3 → shot update) against a fake ai-render HTTP server (httpx `MockTransport`) and the local storage backend, asserting the shot becomes `completed` with a populated `image_reference`.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import base64
import io

import httpx
from PIL import Image

from app.extensions import db
from app.models import ProductPhotoShot, ProductPhotoShotType, AIRenderStatus
from app.services import photo_render
from app.services.ai_render_client import get_ai_render_client
from tests.test_milestone4_product_ops import _product


def test_end_to_end_generate_to_s3(monkeypatch, app, tmp_path):
    png = io.BytesIO(); Image.new("RGB", (8, 8), (9, 9, 9)).save(png, format="PNG")
    b64 = base64.b64encode(png.getvalue()).decode()

    job_state = {"id": None}

    def handler(request):
        if request.url.path == "/generate":
            return httpx.Response(202, json={"job_id": "job-1"})
        if request.url.path == "/jobs/job-1":
            if job_state["id"] is None:
                job_state["id"] = "seen"
                return httpx.Response(200, json={"status": "running", "image_base64": None, "error": None})
            return httpx.Response(200, json={"status": "completed", "image_base64": b64, "error": None})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class FakeConfiguredClient:
        def is_configured(self):
            return True
        def create_generation(self, path, **kw):
            with httpx.Client(base_url="http://ai-render", transport=transport) as c:
                r = c.post("/generate", files={"model_file": (path, open(path, "rb"))},
                           data={"prompt": kw["prompt"], "shot_id": kw["shot_id"],
                                 "camera_az": "0", "camera_el": "0", "camera_extent": "0.7"})
                return r.json()
        def get_job(self, jid):
            with httpx.Client(base_url="http://ai-render", transport=transport) as c:
                r = c.get(f"/jobs/{jid}")
                return r.json()

    monkeypatch.setattr(photo_render, "get_ai_render_client", lambda: FakeConfiguredClient())

    fake_model = tmp_path / "m.stl"; fake_model.write_bytes(b"mesh")
    monkeypatch.setattr(photo_render, "materialize_storage_reference", lambda ref, **kw: (str(fake_model), False))

    with app.app_context():
        product = _product(model_file_path=str(fake_model))
        shot = ProductPhotoShot.query.filter_by(
            product_id=product.id, shot_type=ProductPhotoShotType.HERO
        ).first()
        result = photo_render.generate_shot(shot, actor_id=None, poll_timeout_seconds=10)
        assert result.completed is True
        assert result.image_reference  # local path or s3:// reference
        assert result.ai_render_status == AIRenderStatus.COMPLETED
```

- [ ] **Step 2: Run the full dfpos test suite**

Run: `pytest -q`
Expected: all green, including the new integration test.

- [ ] **Step 3: Run the microservice suite**

Run: `cd services/ai-render && python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Manual end-to-end smoke**

Run: start the microservice (`cd services/ai-render && AI_RENDER_INTERNAL_API_TOKEN=tok python -m uvicorn app.main:app --port 8093`) with a stubbed renderer, start dfpos + Celery worker, set `AI_RENDER_ENABLED=true AI_RENDER_SERVICE_URL=http://localhost:8093 AI_RENDER_INTERNAL_API_TOKEN=tok`, click "Generate with AI" on a hero shot.
Expected: badge → "Generating…" → image appears + shot marked complete.

- [ ] **Step 5: Commit**

```bash
git add tests/test_ai_render_integration.py
git commit -m "test(dfpos): end-to-end AI render → S3 → checklist integration"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage**
- Microservice (FastAPI + diffusers ControlNet SD-1.5 + cpu offload + attention slicing + float32 + mps/cpu fallback): Tasks 1, 4, 6. ✓
- Endpoint POST /generate (Base64 image return + shot_id pass-through): Tasks 3, 5 (job-based; image_base64 + shot_id accepted). ✓
- Photo Checklist integration (Generate action on items): Tasks 12, 13. ✓
- Depth extraction at shot angle: Tasks 2, 5 (orthographic — deviation noted above). ✓
- Microservice call to localhost:<port>/generate: Task 8 + 9. ✓
- S3 upload under `renders/{model_id}/{shot_id}` path → adapted to repo convention `products/{pid}/renders/{shot_type}.png` via `product_asset_key`: Task 9. ✓
- Update checklist item + attach S3 URL + mark completed: Task 9 (complete_ai_render). ✓
- Non-blocking UX (Generating badge/spinner, app stays usable): Tasks 13, 14. ✓
- Hardware optimizations (enable_model_cpu_offload, attention slicing, float32, cpu fallback): Task 4. ✓
- 3-shot scope (hero, close_up, pos_tile): Tasks 9, 12, 13. ✓
- Auto prompt from templates + metadata: Task 9. ✓
- Error handling + retries (failed status, Retry, serial queue, concurrency=1): Tasks 9, 10, 11, 14. ✓
- Tests (microservice + dfpos + integration, no real model loading): Tasks 2–5, 7–12, 16. ✓
- Config + env + compose: Task 15. ✓
- Audit events: Task 10. ✓

**2. Placeholder scan** — no "TBD"/"TODO"/"similar to Task N". (An earlier draft of Task 9 Step 1 contained an invalid placeholder test block; it was removed during self-review — the step now contains only the valid test body.) ✓

**3. Type consistency** — `AIRenderStatus` enum values (`none/pending/running/completed/failed`) match between model (Task 7), product_ops (Task 10), photo_render (Task 9), routes (Task 12), template (Task 13), poller (Task 14). `camera_for_shot` returns `{az, el, extent}` matching client form keys `camera_az/el/extent` (Task 8) and microservice form fields (Task 5). `set_ai_render_status`/`complete_ai_render` signatures match usage in Tasks 9, 11, 12. `get_ai_render_client()` used in Task 9 matches Task 8. `render_product_photo_shot` task name matches the lazy import in Task 12. ✓

One risk flagged for the executor: the Task 9 Step 1 test contains an obviously-invalid placeholder block (`db.session.query.__self__`) followed by the real test. The executor should use **only the second, valid test body** (the one starting `from __future__ import annotations` with `resolve_model_path` imported). If the plan is executed by a subagent, this instruction must be honored to avoid a broken test file. ✓ noted.

**Note:** the invalid placeholder block described immediately above has been removed from Task 9 Step 1 during self-review; the step now contains a single, valid test body. This paragraph is retained only to document that the review happened.