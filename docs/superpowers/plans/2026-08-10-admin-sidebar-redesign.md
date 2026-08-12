# Admin Sidebar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the long flat authenticated sidebar with a workflow-first grouped sidebar that keeps every existing destination reachable.

**Architecture:** Keep the current Flask context model and theme tokens, but rebuild the sidebar template around explicit group data and Alpine-powered disclosures. Preserve route/module enforcement exactly as-is and limit behavior changes to navigation layout and visibility.

**Tech Stack:** Flask, Jinja2, Alpine.js, Tailwind utility classes, existing theme tokens

## Global Constraints

- Do not remove any menu item or route destination from the authenticated navigation.
- Use design tokens instead of hardcoded colors.
- Keep the current mobile off-canvas sidebar behavior.
- Preserve existing `active_section` server-side context and module gating.
- Make group disclosure behavior clearer without turning the admin app into a SPA.

---

### Task 1: Add regression coverage for grouped sidebar behavior

**Files:**
- Modify: `tests/test_app.py`
- Inspect: `app/templates/components/_sidebar.html`

**Interfaces:**
- Consumes: authenticated page responses rendered through the existing Flask test client
- Produces: sidebar assertions that prove quick access, grouped headings, and preserved destinations render for an authenticated admin user

- [ ] **Step 1: Write the failing test**

```python
def test_authenticated_sidebar_uses_grouped_navigation(client, app):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = db.session.query(User).filter_by(email=app.config["ADMIN_EMAIL"]).one()

    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.get("/dashboard/")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick access" in html
    assert "Sell" in html
    assert "Make" in html
    assert "Stock" in html
    assert "Money" in html
    assert "Grow" in html
    assert "System" in html
    assert "Dashboard" in html
    assert "Notifications" in html
    assert "POS" in html
    assert "Categories" in html
    assert "Collections" in html
    assert "Feature Flags" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_authenticated_sidebar_uses_grouped_navigation -v`

Expected: FAIL because the current sidebar does not render the new grouped headings like `Quick access` and `Sell`.

- [ ] **Step 3: Write minimal implementation**

```jinja
{# Replace flat navigation with grouped sections #}
{% set sidebar_groups = [...] %}
{% for group in sidebar_groups %}
  <section x-data="{ open: ... }">
    <button type="button">...</button>
    <div x-show="open">...</div>
  </section>
{% endfor %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_authenticated_sidebar_uses_grouped_navigation -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_app.py app/templates/components/_sidebar.html
git commit -m "feat: regroup admin sidebar navigation"
```

### Task 2: Implement grouped sidebar structure and disclosure behavior

**Files:**
- Modify: `app/templates/components/_sidebar.html`
- Inspect: `app/__init__.py`

**Interfaces:**
- Consumes: `active_section`, `unread_notification_count`, `is_module_enabled`, and existing route helpers
- Produces: grouped sidebar sections with auto-open active group behavior and visible child destinations within expanded groups

- [ ] **Step 1: Write the failing test**

```python
def test_active_sidebar_group_expands_for_product_pages(client, app):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = db.session.query(User).filter_by(email=app.config["ADMIN_EMAIL"]).one()

    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.get("/products/studio")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "x-data=\"{ open: true }\"" in html or "x-data=\"{ open: false }\"" in html
    assert "Categories" in html
    assert "Collections" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_active_sidebar_group_expands_for_product_pages -v`

Expected: FAIL because the current template does not define grouped disclosure sections.

- [ ] **Step 3: Write minimal implementation**

```jinja
{% set make_open = active_section in ["products", "print_jobs", "printers"] %}
<section x-data="{ open: {{ 'true' if make_open else 'false' }} }">
  <button type="button" @click="open = !open">Make</button>
  <div x-show="open">
    <a href="{{ url_for('products.studio') }}">Products</a>
    <a href="{{ url_for('products.list_resource', resource_key='categories') }}">Categories</a>
    <a href="{{ url_for('products.list_resource', resource_key='collections') }}">Collections</a>
  </div>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_active_sidebar_group_expands_for_product_pages -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/templates/components/_sidebar.html tests/test_app.py
git commit -m "feat: add collapsible workflow groups to sidebar"
```

### Task 3: Run focused verification for sidebar regressions

**Files:**
- Verify: `app/templates/components/_sidebar.html`
- Verify: `tests/test_app.py`

**Interfaces:**
- Consumes: new sidebar template and focused tests
- Produces: evidence that the grouped navigation renders and preserves destination access

- [ ] **Step 1: Run the focused sidebar tests**

```bash
uv run pytest tests/test_app.py::test_authenticated_sidebar_uses_grouped_navigation tests/test_app.py::test_active_sidebar_group_expands_for_product_pages -v
```

- [ ] **Step 2: Run one existing app smoke test**

```bash
uv run pytest tests/test_app.py::test_home_page_loads -v
```

- [ ] **Step 3: Review the output and confirm no sidebar regression signal remains**

```text
Expected:
- new sidebar tests PASS
- smoke test PASS
- no import/template/render errors
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/components/_sidebar.html tests/test_app.py docs/superpowers/specs/2026-08-10-admin-sidebar-redesign-design.md docs/superpowers/plans/2026-08-10-admin-sidebar-redesign.md
git commit -m "docs: capture admin sidebar redesign plan"
```
