---
name: Bug report
about: Report something that is broken or behaving unexpectedly
title: "Bug: "
labels: bug, priority:medium
assignees: ""
---

## Describe the bug
A clear and concise description of what is broken.

## Steps to reproduce
1. Go to ...
2. Click on ...
3. See error

## Expected behavior
What you expected to happen.

## Actual behavior
What actually happened (include error messages, stack traces, screenshots).

## Environment
- Environment (local / Docker / production):
- Browser / device (if frontend):
- Relevant module (POS, products, receipts, analytics, markets, etc.):

## Compliance check
<!-- Definition of Done — every bug fix must keep compliance safe. -->
- [ ] The fix does not expose, sell, or publish products whose model license status is `personal_only`, `restricted`, or `needs_review`.
- [ ] License/compliance fields (`license_status`, `model_license_*`, `story_internal_compliance_notes`) remain accurate and are surfaced in admin where relevant.
- [ ] No card data, CVV, or card number fields were introduced.
- [ ] No secrets or API keys were committed.

## Definition of Done
- [ ] Root cause identified
- [ ] Regression test added
- [ ] Audit logging covers the affected action (if meaningful)
- [ ] Feature flag / permission enforcement intact (if applicable)
- [ ] Compliance check above passes
- [ ] `uv run ruff check .` and `uv run pytest -v --tb=long` pass
