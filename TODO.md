# TODO.md

This file is the live working list for AI agents and humans collaborating in this repo.

## How To Use This File

- Read this file after `PROMPTS.md` and before making a plan.
- Update it when work starts, when scope changes, and when work completes.
- Keep items concrete and implementation-oriented.
- Mark completed work instead of deleting it immediately so recent progress stays visible.
- Prefer short status tags: `todo`, `in-progress`, `blocked`, `done`.

## Current Focus

- `done` Reorganized agent guidance into `AGENTS.md`, `PROMPTS.md`, `ARCHITECTURE.md`, and this file.
- `done` Built the public website + ecommerce storefront pass: polished public pages, session cart, online checkout, and payment fallback flow.
- `done` Refactored product asset storage so uploaded model/image/generated files follow the per-product and per-variant folder layout used in production file management.
- `done` Rebuilt Product Studio into isolated primary and variant accordions so each section owns its own fields, assets, previews, and cost calculations.
- `todo` Keep `ARCHITECTURE.md` aligned with the real codebase as modules and services evolve.
- `todo` Keep `PROMPTS.md` aligned with the team’s preferred build workflow and review habits.

## Next Priorities

- `todo` Compare implemented modules against the required modules list in `AGENTS.md` and note gaps.
- `todo` Audit API coverage under `/api/v1/` against the required resource list.
- `todo` Audit admin CRUD coverage for modules that now exist in models/services but may still need full UI flows.
- `todo` Review test coverage against the minimum expectations in `AGENTS.md`.

## Parking Lot

- `todo` Decide later whether a separate `ROADMAP.md` is still useful for longer-term planning beyond the active working list.
- `todo` Add milestone-based phases here if the project shifts from feature work into release planning.

## Recently Completed

- `done` Added public storefront checkout with session cart, customer checkout form, Square payment-link integration, and Venmo fallback confirmation flow.
- `done` Upgraded the public website with richer home/shop/product pages plus 3D printing basics, returns, and customer policies pages.
- `done` Added focused storefront tests covering cart, Venmo checkout, and Square redirect behavior.
- `done` Added a dedicated live task tracker for agents.
- `done` Established a place for architecture-specific guidance outside `AGENTS.md` and `DESIGN.md`.
- `done` Established a dedicated prompts/workflow file for session-level agent behavior.
