---
name: Feature request
about: Suggest a new feature or improvement
title: "Feature: "
labels: enhancement, priority:medium
assignees: ""
---

## Problem statement
What question does this answer or what problem does it solve? (e.g. "What should we make, sell, restock, or prepare next?")

## Proposed solution
A clear description of the feature and how it should behave.

## Alternatives considered
Any other approaches that were considered and why they were not chosen.

## Scope
- [ ] Public website
- [ ] Admin dashboard
- [ ] POS
- [ ] REST API
- [ ] Service / business logic
- [ ] Data model / migration

## Affected modules
Use module labels (e.g. `module:pos`, `module:products`, `module:receipts`, `module:analytics`, `module:cost-engine`, `module:prep-tasks`).

## Compliance check
<!-- Definition of Done — new features must keep licensing safe. -->
- [ ] Feature does not assume rights to official logos, insignia, marks, university marks, copyrighted characters, or trademarked designs.
- [ ] Feature records/surfaces product & model license status (`license_status`, `model_license_*`, `story_internal_compliance_notes`) where products/designs are involved.
- [ ] No real card processing, card number fields, or CVV fields.
- [ ] No secrets or API keys committed; `.env.example` updated for new config.

## Definition of Done
- [ ] Models/migrations if schema changes
- [ ] Forms/schemas if it accepts input
- [ ] Admin pages where needed
- [ ] API endpoints where required
- [ ] Validation + error handling + user feedback
- [ ] Feature flag / permission enforcement where relevant
- [ ] Audit logging for meaningful actions
- [ ] Tests where practical
- [ ] Compliance check above passes
- [ ] `uv run ruff check .` and `uv run pytest -v --tb=long` pass
