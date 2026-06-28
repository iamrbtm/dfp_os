# ARCHITECTURE.md

This document is the technical guide for how Dude Fish OS is structured today and how new work should fit into the system.

## Purpose

Use this file for:

- Folder structure and module boundaries
- Application data flow
- State management choices
- Service-to-service and module-to-module interaction rules
- Expansion guidance for future agents

Keep business goals, feature requirements, and acceptance criteria in `AGENTS.md` and `DESIGN.md`. Keep active task tracking in `TODO.md`. Keep session workflow instructions in `PROMPTS.md`.

## System Shape

The project is a Flask-first monolith with one supporting microservice:

- Main app: public website, admin dashboard, POS, REST API, analytics, auth, and operational workflows
- Audit log service: isolated service under `services/audit-log/` for durable audit event ingestion and retrieval

The main app should remain the source of truth for business operations. Add microservices only when there is a clear operational reason such as isolation, scale boundaries, or independent deployment needs.

## Folder Structure

Expected top-level structure:

```text
app/
  blueprints/
  forms/
  models/
  schemas/
  services/
  static/
  templates/
  utils/
services/
  audit-log/
migrations/
tests/
uploads/
AGENTS.md
ARCHITECTURE.md
DESIGN.md
PROMPTS.md
TODO.md
```

Current main app conventions:

- `app/__init__.py`: application factory and app bootstrap
- `app/config.py`: configuration objects and environment-driven settings
- `app/extensions.py`: Flask extension initialization
- `app/cli.py`: CLI commands such as demo seeding
- `app/models/`: persistence models and shared base behavior
- `app/blueprints/`: route registration grouped by domain
- `app/forms/`: browser form validation and UI-facing form logic
- `app/schemas/`: API validation, serialization, and response contracts
- `app/services/`: business logic, orchestration, and reusable domain operations
- `app/templates/`: server-rendered Jinja UI
- `app/static/`: Tailwind source, compiled assets, and lightweight browser behavior
- `app/utils/`: small cross-cutting helpers

## Blueprint Boundaries

Blueprints should map to user-facing domains or operational areas, not arbitrary technical layers.

Current domains include:

- `public`
- `auth`
- `dashboard`
- `products`
- `inventory`
- `printers`
- `print_jobs`
- `customers`
- `orders`
- `custom_orders`
- `markets`
- `expenses`
- `analytics`
- `pos`
- `api`
- `settings`
- `api_tokens`

Rules:

- Keep routes thin.
- Put business logic in services.
- Put HTML form handling in forms.
- Put API contracts in schemas.
- Prefer domain-specific helpers over route-local ad hoc logic.

## Data Flow

### Browser Request Flow

Standard browser flow:

1. Request enters a blueprint route.
2. Route validates browser input with WTForms where needed.
3. Route calls a service for domain logic.
4. Service reads or writes SQLAlchemy models.
5. Route returns a Jinja template, redirect, flash message, or HTMX partial.

### API Request Flow

Standard API flow:

1. Request enters `/api/v1/` through the API blueprint.
2. Auth is resolved through API token validation.
3. Request payloads are validated with schemas.
4. Services perform domain logic and persistence.
5. Response is serialized to JSON with consistent structure and status codes.

### POS Flow

POS should stay fast and task-oriented:

1. Authenticated staff opens a POS session.
2. POS UI loads products and categories optimized for quick touch interaction.
3. Cart changes happen with lightweight client state plus server validation.
4. Checkout creates order, payment, and inventory effects atomically.
5. Session closeout summarizes totals by payment method and market attribution.

## State Management Choices

Default state strategy:

- Server is the source of truth.
- Database is the durable business state.
- Jinja pages should prefer server-rendered state.
- HTMX may be used for narrow inline updates.
- Alpine.js should stay limited to tiny UI behaviors.
- Avoid large client-side state unless there is a clear UX payoff.

For POS specifically:

- A small local client cart state is acceptable for speed.
- Pricing, inventory deduction, and sale completion must be validated server-side.
- Do not let the POS become the architecture template for the whole product.

Avoid:

- SPA-first patterns across the main app
- Duplicated business rules in browser code and server code
- Client-side authority over money, permissions, or inventory truth

## Module Interaction Rules

Preferred dependency direction:

```text
blueprints -> forms/schemas -> services -> models
```

Supporting utilities may be used across layers when they remain small and generic.

Rules:

- Blueprints may call services directly.
- Services may coordinate multiple models.
- Services may call other services when the boundary is clear and acyclic.
- Models should not contain sprawling business workflows.
- Schemas should not become service layers.
- Forms should not become persistence layers.

## Main Domain Interactions

Key cross-module interactions:

- Product Studio records, categories, and collections drive public catalog, POS visibility, and inventory records.
- Inventory connects product records to physical locations and powers restock and POS deduction workflows.
- Orders connect customers, line items, payments, channels, and fulfillment.
- Custom requests may create deposits, customer records, and follow-on orders.
- Markets and POS sessions provide market attribution for sales and analytics.
- Printers, AMS units, filament, and print jobs support production planning and failure tracking.
- Expenses and payments feed profitability and market performance analytics.
- API tokens control access to `/api/v1/`.
- Audit logging should capture important admin and operational mutations.

## Microservice Interaction

The audit log service is the current supporting service. Treat it as infrastructure for compliance and change history, not as a home for unrelated business logic.

Guidelines:

- The Flask app owns the business action.
- The audit service records the event produced by that action.
- Write application code so business operations still behave safely if audit delivery is degraded.
- Keep the audit event schema explicit and versionable.
- Avoid spreading core business logic across the main app and the audit service.

## Database and Persistence Guidance

- MariaDB is the primary database for the main app.
- Use SQLAlchemy ORM and Flask-Migrate for schema evolution.
- Use UTC timestamps.
- Use `Numeric(10, 2)` or integer cents for money.
- Prefer soft delete or archival for important records where practical.
- Add indexes for commonly filtered fields such as slugs, SKUs, statuses, order numbers, emails, dates, and token hashes.

## Frontend Architecture

- Public site, admin, and most back-office UI should remain Jinja + Tailwind + vanilla JavaScript.
- HTMX is encouraged for scoped interactions where it reduces page reload friction.
- Alpine.js is acceptable for tiny interactivity, not for app-wide state.
- Chart.js is the standard choice for analytics visuals.
- If POS needs a richer island later, keep it isolated to POS assets and routes only.

## Testing Strategy

Test at the behavior level first:

- App factory boot
- Auth and authorization gates
- Core CRUD flows
- API auth and JSON responses
- POS sale lifecycle
- Inventory and order side effects
- Analytics summary contracts
- CLI seed behavior

When adding architecture:

- Add tests around service behavior before adding incidental UI-only tests.
- Prefer covering cross-module workflows where bugs would be expensive.

## Documentation Maintenance Rules

- Update this file when new modules, services, or interaction patterns are introduced.
- If the real codebase diverges from this document, fix the document or the code in the same workstream.
- Do not bury session-specific instructions here; place those in `PROMPTS.md`.
