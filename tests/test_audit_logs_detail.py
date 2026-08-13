"""Integration tests for the audit event detail timeline."""

from __future__ import annotations

from unittest.mock import MagicMock


SAMPLE_EVENT = {
    "id": "evt-abc",
    "idempotency_key": None,
    "tenant_id": None,
    "occurred_at": "2026-06-15T10:00:00Z",
    "received_at": "2026-06-15T10:00:01Z",
    "actor_id": "1",
    "actor_type": "user",
    "actor_display_name": "Admin User",
    "action": "order.created",
    "entity_type": "order",
    "entity_id": "42",
    "source_service": "dfp-os",
    "source_module": "app.services.orders",
    "request_id": "req-1",
    "ip_address": "10.0.0.1",
    "user_agent": "test-agent",
    "before_state": {},
    "after_state": {"status": "draft"},
    "metadata": None,
    "hash": "h-abc",
    "previous_hash": "h-prev",
}


SAMPLE_TIMELINE = [
    {
        "id": "evt-abc",
        "action": "order.created",
        "entity_type": "order",
        "entity_id": "42",
        "actor_display_name": "Admin User",
        "actor_type": "user",
        "source_module": "app.services.orders",
        "occurred_at": "2026-06-15T10:00:00Z",
        "chain_status": "head",
    },
    {
        "id": "evt-def",
        "action": "order.updated",
        "entity_type": "order",
        "entity_id": "42",
        "actor_display_name": "Admin User",
        "actor_type": "user",
        "source_module": "app.services.orders",
        "occurred_at": "2026-06-15T11:00:00Z",
        "chain_status": "ok",
    },
]


def _stub_client(event, timeline):
    client = MagicMock()
    client._is_configured.return_value = True
    client.get.return_value = event
    client.entity_timeline.return_value = timeline
    return client


def test_audit_logs_detail_renders_timeline(app, client, login_admin):
    """A detail page for an event with an entity_type + entity_id
    should render the timeline partial with the current event marked.
    """
    with app.test_request_context():
        from app.blueprints.audit_logs import routes

        original = routes.get_audit_client
        try:
            routes.get_audit_client = lambda: _stub_client(SAMPLE_EVENT, SAMPLE_TIMELINE)
            response = client.get("/audit-logs/evt-abc")
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'id="audit-timeline"' in html
            assert "YOU ARE HERE" in html
            assert "order.created" in html
            assert "order.updated" in html
        finally:
            routes.get_audit_client = original


def test_audit_logs_detail_handles_event_without_entity(app, client, login_admin):
    """Events with no entity_type should render a friendly empty state
    rather than blowing up.
    """
    event = dict(SAMPLE_EVENT)
    event["id"] = "evt-orphan"
    event["entity_type"] = ""
    event["entity_id"] = ""

    with app.test_request_context():
        from app.blueprints.audit_logs import routes

        original = routes.get_audit_client
        try:
            client_stub = _stub_client(event, [])
            routes.get_audit_client = lambda: client_stub
            response = client.get("/audit-logs/evt-orphan")
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'id="audit-timeline"' in html
            # The partial's "no events" copy.
            assert "No events for this record" in html
            # Scope toggle hidden when there is no entity.
            assert "All order events" not in html
        finally:
            routes.get_audit_client = original


def test_audit_logs_detail_scope_type_returns_broader_timeline(app, client, login_admin):
    """When scope=type is set, the timeline should include every
    event of that entity_type (across all records), not just this one.
    """
    type_timeline = [
        {
            "id": "evt-abc",
            "action": "order.created",
            "entity_type": "order",
            "entity_id": "42",
            "actor_display_name": "Admin User",
            "occurred_at": "2026-06-15T10:00:00Z",
            "chain_status": "head",
        },
        {
            "id": "evt-99",
            "action": "order.created",
            "entity_type": "order",
            "entity_id": "99",
            "actor_display_name": "Admin User",
            "occurred_at": "2026-06-15T09:00:00Z",
            "chain_status": "ok",
        },
    ]
    with app.test_request_context():
        from app.blueprints.audit_logs import routes

        original = routes.get_audit_client
        try:
            routes.get_audit_client = lambda: _stub_client(SAMPLE_EVENT, type_timeline)
            response = client.get("/audit-logs/evt-abc?scope=type")
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'id="audit-timeline"' in html
            assert "All order events" in html
        finally:
            routes.get_audit_client = original


def test_audit_logs_detail_returns_partial_on_htmx_request(app, client, login_admin):
    """An HX-Request with partial=timeline should return only the
    timeline partial, not the full page.
    """
    with app.test_request_context():
        from app.blueprints.audit_logs import routes

        original = routes.get_audit_client
        try:
            routes.get_audit_client = lambda: _stub_client(SAMPLE_EVENT, SAMPLE_TIMELINE)
            response = client.get(
                "/audit-logs/evt-abc?partial=timeline",
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'id="audit-timeline"' in html
            # Should NOT include the detail-page header content.
            assert "Integrity chain" not in html
        finally:
            routes.get_audit_client = original
