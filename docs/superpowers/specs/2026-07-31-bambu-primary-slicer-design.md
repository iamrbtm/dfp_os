# Bambu-Primary Product Slicing Design

## Objective

Make Bambu Studio the primary engine in the existing DFPos slicer microservice and retain
PrusaSlicer as the secondary engine for product analysis and cost estimation. Wire the engine-aware
result through the existing staged Product Studio workflow: save a product draft, upload a model,
analyze it asynchronously, store the generated artifact, and update product cost estimates.

Printer submission, printer credentials, MQTT, FTP, Bambu Connect, Bambu Farm Server, and physical
print controls are outside this phase.

## Confirmed product decisions

- Product creation remains staged. The basic product is saved before a model is uploaded.
- Model upload automatically starts asynchronous validation, slicing, artifact storage, and costing.
- Bambu Studio is attempted first and PrusaSlicer second.
- The first Bambu profile matrix supports the installed fleet's standard 0.4 mm nozzles only.
- OrcaSlicer is not included.
- Both engines remain behind one stable slicer-service API.
- Future printer communication will be implemented behind a separate printer-gateway boundary.

## Architecture

```text
Product Studio model upload
        |
        v
Celery model-analysis task
        |
        v
DFPos slicer microservice
        |-- Bambu Studio adapter (primary)
        `-- PrusaSlicer adapter (secondary)
        |
        v
Immutable sliced artifact + estimates + engine metadata
        |
        v
ProductAnalysisRun, ProductModelAsset and Product cost summaries
```

The slicer microservice owns engine discovery, engine selection, command construction, profile
resolution, subprocess isolation, estimate extraction, artifact validation, and fallback policy.
The Flask application requests a slice using engine-neutral product settings and persists the
returned result. It does not construct Bambu or Prusa command lines.

Both pinned slicer runtimes are installed in the prebuilt slicer base image. Application source and
Python dependency changes therefore do not reinstall the slicers.

## Engine interface

Each engine adapter implements the same internal behavior:

- Report availability and exact version.
- Validate whether it supports the requested printer, nozzle, material, and purpose.
- Generate an engine-specific command without invoking a shell.
- Slice a supplied model inside an isolated temporary directory.
- Return the artifact filename, media type, bytes, SHA-256, profile identity, estimates, and
  diagnostic metadata.
- Classify failures as either fallback-eligible engine failures or terminal request/configuration
  failures.

The engine order defaults to `bambu,prusa`. The application may report the preference in a request,
but callers cannot introduce an unconfigured executable or arbitrary command.

## Profile policy

The supported printer identifiers are:

- `bambu_a1`
- `bambu_p1p`
- `bambu_x1c`

The Bambu adapter accepts only a 0.4 mm nozzle in this phase. Printer, process, filament, and build
plate choices resolve through an allowlisted mapping to version-pinned Bambu configuration files.
User-supplied filesystem paths are never accepted as profiles.

The existing product form continues to collect printer, material, layer height, walls, top and
bottom layers, infill, supports, brim, copies, scale, orientation, embedded-setting preference, and
artifact-retention preference. The slicer service validates and translates supported settings for
the selected engine. Unsupported printer/nozzle/profile combinations fail clearly rather than
silently changing the production recipe.

## Product model-analysis data flow

1. An authenticated user saves a product draft.
2. The user uploads an STL, 3MF, or OBJ and selects the supported product-analysis settings.
3. DFPos creates a source `ProductModelAsset` and a current `ProductAnalysisRun` containing a
   sanitized, engine-neutral settings snapshot.
4. The Celery task validates and scales the model using the existing geometry pipeline.
5. The task sends the model and settings to the slicer microservice with Bambu first and Prusa
   second.
6. The slicer service attempts Bambu Studio.
7. On an eligible Bambu engine failure, it attempts PrusaSlicer and retains the Bambu diagnostic.
8. The service streams the resulting binary artifact and compact result metadata to the Flask
   client. Large artifacts are not embedded in JSON.
9. The task uploads the artifact through the existing product-storage service and records its
   checksum and media type as a `ProductModelAsset`.
10. The task records engine, version, fallback state, profiles, estimates, artifact metadata, and
    diagnostics in the analysis run's slicer statistics.
11. Existing cost-engine integration recalculates product material cost, print time, profit, and
    the immutable cost snapshot.
12. The Product Studio renders the result and warns when Prusa was used as an estimate-only
    fallback.

The existing analysis-run history provides versioned recipe settings and immutable run results for
this phase. A separate production-recipe table is deferred until DFPos needs multiple active
recipes per product.

## Artifact contract

A successful Bambu slice preserves the native sliced `.gcode.3mf` artifact. A successful Prusa
fallback preserves its generated `.gcode` artifact. The result metadata includes:

- Engine key and display name.
- Exact engine version.
- `fallback_used` and the primary-engine failure diagnostic when applicable.
- Printer, process, filament, and build-plate profile identities.
- Filament grams, print minutes, layer count, and available cost statistics.
- Artifact filename, media type, size, and SHA-256.
- Whether the artifact is eligible for future Bambu direct-print submission.

The slicer API adds `POST /api/v1/slice-artifact` for the product pipeline. A successful request
returns the artifact bytes as the response body, the artifact media type as `Content-Type`, the
filename in `Content-Disposition`, and compact base64url-encoded JSON metadata in the
`X-DFPOS-Slicer-Metadata` response header. The encoded metadata must remain below 6 KiB; extended
subprocess output stays in service logs. Validation and execution failures return structured JSON.
The existing JSON `/api/v1/slice` behavior remains available during the transition.

## Fallback policy

Prusa fallback is automatic for product analysis and costing when Bambu Studio:

- Is unavailable.
- Times out or crashes.
- Exits unsuccessfully.
- Does not produce a valid artifact.
- Produces an artifact without the required time or filament estimates.

Fallback is not attempted for:

- An unsupported printer.
- A nozzle other than 0.4 mm.
- An invalid material, process, or profile request.
- An unsafe or unsupported file type.
- Authentication or request-validation failure.

The engine actually used is always persisted and displayed. A Prusa fallback result is explicitly
estimate-only for future direct-print purposes. A future print-start workflow must not silently
substitute Prusa output for a Bambu-native production artifact.

## Health and operations

The readiness response reports each engine independently, including availability and version:

- `primary`: Bambu is available; Prusa may be available or unavailable.
- `fallback_only`: Bambu is unavailable and Prusa is available.
- `unhealthy`: neither engine is available.

The service remains ready in `fallback_only` mode so product estimates can continue. Logs and
health data make the degradation visible.

The prebuilt base image pins both slicer versions and verifies externally downloaded Bambu assets
with SHA-256. Profile resources are pinned with the runtime instead of updating during a request.

## Security and safety

- Both slicers run as the non-root `appuser`.
- Subprocesses receive argument arrays and never use shell execution.
- Uploaded filenames are reduced to safe basenames.
- Temporary workspaces are isolated and removed on success and failure.
- File-size, file-type, subprocess-time, and container-memory limits remain enforced.
- Profile selection uses allowlisted identifiers rather than filesystem paths.
- The slicer container receives no printer credentials and requires no printer-network access.
- Engine diagnostics are retained for administrators without leaking internal filesystem paths to
  ordinary users.
- No Docker volumes or database data are removed as part of this work.

## Product Studio presentation

The existing analysis panel displays:

- Bambu Studio or PrusaSlicer fallback.
- Engine version and selected printer profile.
- Estimated time, filament, cost, and copies.
- Stored artifact type.
- A visible warning when fallback was used and the artifact is estimate-only.
- A concise administrator diagnostic explaining why Bambu failed.

The basic product form remains available even when the slicer service is degraded. Model analysis
can fail and be retried without deleting or rolling back the product draft.

## Testing and verification

Automated tests cover:

- Bambu adapter profile resolution and command construction.
- Bambu estimate extraction and `.gcode.3mf` validation.
- Bambu-first engine selection.
- Eligible Prusa fallback with the original Bambu diagnostic retained.
- Terminal validation failures that do not invoke Prusa.
- Primary, fallback-only, and unhealthy readiness states.
- Binary artifact streaming and client download behavior.
- Product analysis-run persistence, artifact storage, cost recalculation, and audit metadata.
- Product Studio rendering for Bambu and Prusa fallback results.
- Existing Prusa option translation as the secondary engine.

Verification includes the slicer tests, focused Flask product/model-analysis tests, project lint and
format checks, Docker Compose configuration validation, the pinned base-image build, the normal
slicer-image build, and a container health/slice smoke test when the Docker daemon and external
release assets are available.

## Deferred work

- Bambu printer authentication and credential storage.
- Bambu Farm Server SDK, Bambu Connect, MQTT, FTP, or Developer Mode integration.
- Starting, pausing, canceling, or monitoring physical printers.
- OrcaSlicer.
- Nozzle sizes other than 0.4 mm.
- Multiple named production recipes per product.
- Automatic printer or AMS assignment.
