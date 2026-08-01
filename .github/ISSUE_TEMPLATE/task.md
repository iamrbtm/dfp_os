---
name: Task
about: A concrete piece of work for a milestone
title: "Task: "
labels: task, priority:medium
assignees: ""
---

## Goal
What should be true when this task is done.

## Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Compliance check
<!-- Definition of Done — every task must keep licensing safe. -->
- [ ] Product/model license & compliance status is recorded and verified before any public or POS sale (`license_status`, `model_commercial_use_allowed`, `model_license_type`, `model_source_url`, `model_proof_of_license_path`).
- [ ] Designs with `personal_only`, `restricted`, or `needs_review` license status are not sold, published, or advertised.
- [ ] Compliance proof is attached/surfaced in admin for products that go live.
- [ ] No card data fields; no secrets committed.

## Definition of Done
- [ ] Implementation matches AGENTS.md architecture and DESIGN.md tokens
- [ ] Audit logging added for meaningful actions
- [ ] Tests pass (`uv run pytest -v --tb=long`)
- [ ] Ruff passes (`uv run ruff check .` and `uv run ruff format --check .`)
- [ ] Compliance check above passes
- [ ] Docs updated if behavior changes
