 You are continuing DFPos in /mnt/storage/docker/dfpos.

  Read AGENTS.md, DESIGN.md, ARCHITECTURE.md, the full plan at
  docs/superpowers/plans/2026-07-31-bambu-primary-product-slicing.md,
  and the SDD ledger at
  .superpowers/sdd/2026-07-31-bambu-primary-product-slicing/progress.md.

  Important state:
  - Bambu Studio is primary; PrusaSlicer is secondary fallback.
  - Tasks 1–7 are complete and reviewed.
  - Task 8 is in progress/being finalized in the current worktree. Inspect git status and do not discard partial edits.
  - The last committed Task 8 baseline is 75385fa; a later atomic-publication fix may be committed or may still be uncommitted. Finish/review Task 8 before
  starting Task 9.
  - MariaDB-focused tests currently stall before test bodies in db.create_all() during a PyMySQL SSL read. Use bounded retries, record exact output, and do not
  reset/drop the DB.
  - Never delete Docker volumes. Never run docker system prune --volumes. Do not reset databases or remove containers except explicitly named temporary smoke
  containers.
  - Use strict TDD: failing test, minimal implementation, focused tests, review, then commit.
  - Preserve unrelated changes.

  After Task 8 is clean, execute Tasks 9–12 sequentially.

  Task 9 — Product Studio profile matrix and engine results:
  - Change printer form choices to bare keys: bambu_a1, bambu_p1p, bambu_x1c.
  - Normalize old saved .ini values with Path(value).stem.
  - Make nozzle a fixed 0.4 mm select/read-only field; reject tampered values server-side.
  - Never accept engine names, executable paths, or profile filesystem paths from form input.
  - Invalid printer/material/nozzle must return the existing friendly validation response and must not enqueue Celery.
  - Render current analysis metadata in Product Studio: engine name/version, printer/process/filament profile IDs, artifact type, direct-print eligibility,
  fallback warning text, and bounded primary failure reason.
  - Use existing design tokens; no SPA/new page.
  - Run:
    UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -q tests/test_product_studio_model_upload.py tests/test_phase4_ux.py
  - Commit:
    feat(products): show Bambu analysis and Prusa fallback

  Task 10 — Bambu base image and Compose:
  - Modify services/slicer/Dockerfile.base only for the slow runtime layer; do not put apt/package installation back into services/slicer/Dockerfile.
  - Keep FROM python:3.14-slim, Python env vars, appuser, /app and /opt/venv ownership.
  - Install with apt --no-install-recommends:
    prusa-slicer curl libwebkit2gtk-4.1-0 libgl1 ca-certificates
  - Download the pinned official Bambu AppImage:
    https://github.com/bambulab/BambuStudio/releases/download/v02.07.01.62/BambuStudio_ubuntu22.04-v02.07.01.62-20260616195227.AppImage
  - Verify SHA256 exactly:
    2749917af560f3b9a2681429da9c43d00c65d096e1a1c479cc49466634174549
  - Extract with --appimage-extract into /opt/bambu-studio, remove temporary AppImage and apt lists, make runtime files usable by appuser, and run /opt/bambu-
  studio/AppRun --help during build.
  - Compose must keep slicer-base under profile build and normal image dfpos-slicer:${DFPOS_IMAGE_TAG:-local}.
  - Add SLICER_BAMBU_STUDIO_PATH, SLICER_BAMBU_PROFILE_ROOT, SLICER_ENGINE_ORDER, SLICER_SLICE_TIMEOUT_SECONDS, SLICER_METADATA_HEADER_MAX_BYTES, and
  SLICER_MAX_MODEL_BYTES to env/Compose as appropriate.
  - Run:
    docker compose --env-file .env.example config --quiet
    git diff --check -- services/slicer/Dockerfile.base services/slicer/Dockerfile docker-compose.yml .env.example
    cd services/slicer && uv run --extra dev pytest -q app/tests/test_runtime_config.py
  - Commit:
    build(slicer): pin Bambu Studio in local base

  Task 11 — Documentation:
  - Update ARCHITECTURE.md, README.md, docs/product_creation_developer_flow.md, and TODO.md.
  - Document the slicer microservice, Bambu-primary/Prusa-fallback policy, native .gcode.3mf versus estimate-only .gcode, run metadata, generated
  ProductModelAsset linkage, 0.4 mm matrix, and multicolor limitation.
  - Document exact safe operator commands:
    docker build -f services/slicer/Dockerfile.base -t dfpos-slicer-base:local services/slicer
    docker compose --env-file .env.example build slicer
    docker compose --env-file .env.example up -d
    docker compose --env-file .env.example --profile build build slicer-base
  - Explicitly state no command requires volume deletion or docker system prune --volumes.
  - Move the misplaced private-workspace docstring cleanup into the appropriate client method if still present.
  - Mark completed TODO work accurately; future printer-gateway/direct-print work goes to the parking lot.
  - Run git diff --check on docs.
  - Commit:
    docs: explain Bambu-primary product slicing

  Task 12 — Full verification and one-time build:
  - Do not edit unrelated code. If a check exposes an in-scope bug, return to that task’s TDD loop.
  - Run service tests/lint and focused root tests from the plan.
  - Run:
    UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff check .
    UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run ruff format --check .
    UV_CACHE_DIR=/tmp/dfpos-uv-cache uv run pytest -v --tb=long
    docker compose --env-file .env.example config --quiet
    git diff --check
  - Clear build cache only, if required:
    docker builder prune --all --force
    Never remove volumes or use docker system prune --volumes.
  - Build the base once:
    docker build -f services/slicer/Dockerfile.base -t dfpos-slicer-base:local services/slicer
    If Docker is unavailable or the build hangs, stop and report the exact output; do not perform destructive cleanup.
  - Verify non-root:
    docker run --rm --user appuser dfpos-slicer-base:local /opt/bambu-studio/AppRun --help
    docker run --rm --user appuser dfpos-slicer-base:local prusa-slicer --version
  - Build normal slicer twice:
    docker compose --env-file .env.example build slicer
    docker compose --env-file .env.example build slicer
    Confirm the normal Dockerfile starts FROM dfpos-slicer-base:${DFPOS_IMAGE_TAG:-local} and has no apt/Prusa/Bambu install step.
  - Run the mandatory native HTTP smoke from Task 12 Step 8 in the plan. It must use one uniquely named temporary container, a random loopback port, a valid
  token, no mounts/volumes/Compose/DB containers, a >1 MiB STL upload, metadata/SHA/ZIP checks, 206 range, malformed Range 400, unsatisfiable Range 416,
  workspace cleanup polling, and exact temporary cleanup.
  - Finish with a concise summary of commits, tests, blocked DB/Docker checks, and exact future operator commands.

  Task 8 itself is still being finalized in the shared worktree; I’m continuing that review now.
