# Slicer Build Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent routine slicer image rebuilds from reinstalling Debian's official PrusaSlicer package and its runtime dependencies.

**Architecture:** Reorder `services/slicer/Dockerfile` so operating-system setup and the Debian package installation form stable layers before the UV tool is introduced. Pin UV to the immutable digest resolved during the last successful build, while leaving `python:3.14-slim` updateable so base-image security updates still refresh system packages.

**Tech Stack:** Docker BuildKit, Docker Compose, Python 3.14 slim, Debian `prusa-slicer`, Astral UV

## Global Constraints

- Continue installing Debian's official `prusa-slicer` package.
- Continue using `apt-get install -y --no-install-recommends`.
- Do not remove Debian-declared runtime dependencies.
- Keep `python:3.14-slim` as the updateable base image.
- Do not change slicing behavior or API contracts.
- Preserve unrelated working-tree changes.

---

### Task 1: Stabilize and verify the PrusaSlicer image layer

**Files:**
- Modify: `services/slicer/Dockerfile:1-23`
- Reference: `docs/superpowers/specs/2026-07-31-slicer-build-cache-design.md`

**Interfaces:**
- Consumes: Docker BuildKit layer cache and the published UV image manifest `ghcr.io/astral-sh/uv@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded`.
- Produces: `dfpos-slicer:local`, with the Debian PrusaSlicer installation layer independent of UV and application-source changes.

- [ ] **Step 1: Record the current cache-invalidating order**

Run:

```bash
sed -n '1,30p' services/slicer/Dockerfile
```

Expected: `COPY --from=ghcr.io/astral-sh/uv:latest` appears before the `RUN`
instruction that installs `prusa-slicer`.

- [ ] **Step 2: Reorder the system layer and pin UV**

Change the beginning of `services/slicer/Dockerfile` to this exact order:

```dockerfile
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
RUN mkdir -p /opt/venv && chown appuser:appuser /app /opt/venv

# Keep this expensive system layer independent of UV and application changes.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        prusa-slicer curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /usr/local/bin/uv
```

Leave the Python dependency, source, health check, and command instructions
unchanged.

- [ ] **Step 3: Validate the Compose configuration and Dockerfile diff**

Run:

```bash
docker compose config --quiet
git diff --check -- services/slicer/Dockerfile
git diff -- services/slicer/Dockerfile
```

Expected: all commands exit `0`; the diff only moves and pins the UV copy and
updates the system-layer comment.

- [ ] **Step 4: Build the reordered image once**

Run:

```bash
docker compose build slicer
```

Expected: exit `0` and image `dfpos-slicer:local` is built. This first build may
install the Debian packages once because the Dockerfile layer graph changed.

- [ ] **Step 5: Prove the expensive layer is cached**

Run the identical build again:

```bash
docker compose build slicer
```

Expected: exit `0`, and the BuildKit step containing
`apt-get install -y --no-install-recommends prusa-slicer curl` reports `CACHED`.

- [ ] **Step 6: Recreate and verify only the slicer service**

Run:

```bash
docker compose up -d --no-deps slicer
docker compose ps slicer
docker compose exec -T slicer curl -fsS http://127.0.0.1:8092/health/ready
docker compose exec -T slicer prusa-slicer --help
docker compose exec -T slicer python -c "from app.services.slicer import _normalize_fill_density; assert _normalize_fill_density('15%') == '15%'; assert _normalize_fill_density('0.2') == '20%'"
```

Expected: the container reports `healthy`; readiness returns JSON containing
`"status":"ready"` and `"prusa_slicer":"available"`; PrusaSlicer help identifies
version `2.9.2+UNKNOWN`; and the normalization assertions exit `0`.

- [ ] **Step 7: Commit only the Dockerfile change**

```bash
git add services/slicer/Dockerfile
git commit -m "build: cache slicer system dependencies"
```

Expected: the commit contains only `services/slicer/Dockerfile`; unrelated
working-tree files remain untouched.
