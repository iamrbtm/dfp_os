# Slicer Build Cache Design

## Goal

Make routine slicer container rebuilds reuse the expensive Debian PrusaSlicer
installation layer while continuing to install Debian's official `prusa-slicer`
package.

## Current Problem

The slicer Dockerfile copies `uv` from the mutable
`ghcr.io/astral-sh/uv:latest` image before installing PrusaSlicer. When that
source image changes, Docker invalidates every later layer. Debian then
downloads and configures PrusaSlicer and its runtime dependencies again even
when only the slicer application source changed.

## Design

Reorder the Dockerfile so stable system setup and the Debian package
installation happen before the `uv` binary is copied into the image. Pin the
`uv` source image to an immutable digest so Python dependency builds are also
reproducible.

Keep `python:3.14-slim` as the updateable base image. A base-image update may
contain operating-system security fixes and should intentionally invalidate the
PrusaSlicer layer. This is distinct from routine application or Python tooling
changes, which must not invalidate it.

The resulting layer order will be:

1. Python 3.14 slim base image.
2. Application user and filesystem setup.
3. Debian `prusa-slicer` and `curl` installation with
   `--no-install-recommends`.
4. Pinned `uv` binary.
5. Locked Python project dependencies.
6. Slicer application source.

## Cache Behavior

- Application source changes rebuild only the final source layer.
- `pyproject.toml` or `uv.lock` changes rebuild Python dependencies and source.
- A deliberate `uv` digest update rebuilds the UV, Python dependency, and
  source layers, but not the Debian PrusaSlicer layer.
- A Python base-image update rebuilds the system layers, including
  PrusaSlicer, so security and ABI changes are incorporated correctly.
- Explicit Docker cache deletion still requires a full rebuild.

## Error Handling

The existing Docker build remains fail-fast. Failure to download or install the
official Debian package, copy the pinned UV binary, or synchronize locked Python
dependencies must fail the image build. No fallback package source will be
introduced.

## Verification

1. Build the slicer image once after changing the Dockerfile.
2. Build the identical image a second time and confirm the Debian
   PrusaSlicer installation step is reported as `CACHED`.
3. Recreate only the slicer service with `--no-deps`.
4. Confirm the container reports healthy and `/health/ready` returns `200` with
   PrusaSlicer available.
5. Confirm the installed binary identifies itself as Debian's PrusaSlicer
   build and that the fill-density normalization code is present.

## Out of Scope

- Replacing Debian's PrusaSlicer package with an AppImage, archive, or source
  build.
- Removing dependencies declared by the Debian package.
- Creating and publishing a separately maintained slicer base image.
- Changing slicing behavior or API contracts.
