# PROMPTS.md

This file is the session playbook for AI agents working in this repository.

## Read Order

When starting work in this repo:

1. Read `AGENTS.md`.
2. Read `PROMPTS.md`.
3. Read `TODO.md`.
4. Read `DESIGN.md`.
5. Read `ARCHITECTURE.md`.
6. Inspect the relevant code before proposing or making changes.

## Rules Of Engagement

- Treat `TODO.md` as the live working plan and update it as work progresses.
- Do not assume the original scaffold docs are fully current; verify against the real codebase.
- Build in phases unless the user explicitly asks for a larger pass.
- Prefer production-minded solutions over placeholder architecture.
- Keep the app Flask-first and server-rendered by default.
- Keep routes thin and business logic in services.
- Preserve a clean separation between browser form validation and API schema validation.
- Make changes that fit the existing codebase unless the user asks for a larger refactor.
- Do not preserve old architecture solely for compatibility if a cleaner replacement is clearly better and safe.

## Preferred Workflow

For implementation work:

1. Confirm the request against `TODO.md` and update it if needed.
2. Inspect the relevant files, routes, models, services, forms, schemas, and tests.
3. Share a short plan.
4. Implement one logical phase at a time.
5. Run formatting and tests that match the scope when possible.
6. Update `TODO.md` to reflect what changed.
7. Summarize the result, including any remaining gaps or follow-up work.

## Documentation Workflow

- `AGENTS.md` is the source for business rules, required modules, acceptance criteria, and project guardrails.
- `DESIGN.md` is the source for product vision, UX direction, and domain intent.
- `ARCHITECTURE.md` is the source for structure, flow, state, and module interaction guidance.
- `TODO.md` is the live execution tracker.
- Put durable guidance in docs, not only in chat replies.

## Coding Preferences

- Use Python 3.14 and `uv`.
- Keep dependencies compatible with Python 3.14.
- Avoid unnecessary compiled dependencies when a pure Python option is good enough.
- Use Tailwind for styling and keep the public site warm, polished, and family-friendly.
- Keep admin and POS fast, practical, and mobile-friendly.
- Use HTMX where it meaningfully simplifies targeted interactions.
- Use Alpine.js only for small UI behavior.
- Do not turn the app into a SPA.

## Quality Bar

Before considering work done, check for:

- Correct model and migration changes when persistence is involved
- Forms or schemas for user input
- Admin or operator flows where appropriate
- API support where the feature belongs in `/api/v1/`
- Validation and error handling
- User feedback in the UI
- Tests that cover the new or changed behavior
- Documentation updates when project guidance changed

## Review Mode

When asked for a review:

- Focus first on bugs, regressions, security issues, and missing tests.
- Ground findings in concrete files and behavior.
- Keep summaries brief after findings.
