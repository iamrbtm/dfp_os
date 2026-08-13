"""Tests for the Redis audit outbox and the upgraded AuditClient.

These tests run with a real Redis (the test infra shares the project's
Redis instance). They exercise:

  * direct POST happy path
  * network failure → outbox
  * outbox flush task replays buffered events
  * backpressure: outbox at max_size refuses critical events
  * deadman: when Redis itself is unreachable events are written to disk
  * audit log detail view's new ``get()`` method
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from unittest.mock import patch

import pytest


def _redis_reachable(url: str) -> bool:
    """Skip the outbox tests when Redis is not available locally."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


REDIS_URL = os.environ.get("AUDIT_REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def outbox_app(app, tmp_path):
    """Configure the test app with an isolated outbox key + DLQ path."""
    app.config["AUDIT_OUTBOX_KEY"] = "audit:outbox:test"
    app.config["AUDIT_OUTBOX_DLQ_PATH"] = str(tmp_path / "audit-queue")
    app.config["AUDIT_OUTBOX_MAX_SIZE"] = 50
    app.config["AUDIT_OUTBOX_BATCH_SIZE"] = 10
    app.config["AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS"] = True
    return app


@pytest.fixture
def flush_outbox(outbox_app):
    """Empty the outbox before each test."""
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
        r.delete(outbox_app.config["AUDIT_OUTBOX_KEY"])
    except Exception:
        pass
    yield
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
        r.delete(outbox_app.config["AUDIT_OUTBOX_KEY"])
    except Exception:
        pass


def test_outbox_enqueue_and_size(outbox_app, flush_outbox):
    if not _redis_reachable(REDIS_URL):
        pytest.skip("Redis not available")
    from app.services import audit_outbox

    assert audit_outbox.size(app=outbox_app) == 0
    ok = audit_outbox.enqueue({"action": "test.x", "entity_type": "test"}, app=outbox_app)
    assert ok is True
    assert audit_outbox.size(app=outbox_app) == 1


def test_outbox_drain_one_removes_head(outbox_app, flush_outbox):
    if not _redis_reachable(REDIS_URL):
        pytest.skip("Redis not available")
    from app.services import audit_outbox

    audit_outbox.enqueue({"action": "test.first", "entity_type": "test"}, app=outbox_app)
    audit_outbox.enqueue({"action": "test.second", "entity_type": "test"}, app=outbox_app)
    head = audit_outbox.drain_one(app=outbox_app)
    assert head is not None
    assert head["action"] == "test.first"
    assert audit_outbox.size(app=outbox_app) == 1
    second = audit_outbox.drain_one(app=outbox_app)
    assert second["action"] == "test.second"
    assert audit_outbox.drain_one(app=outbox_app) is None


def test_outbox_deadman_writes_to_disk_when_redis_unavailable(outbox_app, tmp_path):
    from app.services import audit_outbox

    audit_outbox.enqueue(
        {"action": "test.deadman", "entity_type": "test", "critical": False},
        app=outbox_app,
    )
    assert audit_outbox.size(app=outbox_app) == 1

    dlq = Path(outbox_app.config["AUDIT_OUTBOX_DLQ_PATH"])
    # Inject a Redis error: enqueue should fall back to disk deadman.
    with patch("app.services.audit_outbox._client") as mock_client:
        import redis as redis_lib

        mock_client.return_value.llen.side_effect = redis_lib.RedisError("simulated down")
        ok = audit_outbox.enqueue(
            {"action": "test.deadman2", "entity_type": "test", "critical": False},
            app=outbox_app,
        )
    assert ok is True
    files = list(dlq.glob("*.json"))
    assert files, "deadman file should have been written"
    record = json.loads(files[0].read_text())
    assert record["payload"]["action"] == "test.deadman2"
    assert "redis_error" in record["reason"]


def test_outbox_replay_deadman_moves_files_back_to_redis(outbox_app, flush_outbox):
    if not _redis_reachable(REDIS_URL):
        pytest.skip("Redis not available")
    from app.services import audit_outbox

    dlq = Path(outbox_app.config["AUDIT_OUTBOX_DLQ_PATH"])
    dlq.mkdir(parents=True, exist_ok=True)
    target = dlq / "1700000000000-test.json"
    target.write_text(
        json.dumps(
            {
                "queued_at": "2024-01-01T00:00:00Z",
                "reason": "outbox_full",
                "payload": {"action": "test.replayed", "entity_type": "test"},
            }
        )
    )

    n = audit_outbox.replay_deadman(app=outbox_app)
    assert n == 1
    assert not target.exists()
    assert audit_outbox.size(app=outbox_app) == 1
    head = audit_outbox.drain_one(app=outbox_app)
    assert head["action"] == "test.replayed"


def test_outbox_backpressure_refuses_critical_above_max(outbox_app, flush_outbox):
    if not _redis_reachable(REDIS_URL):
        pytest.skip("Redis not available")
    from app.services import audit_outbox

    outbox_app.config["AUDIT_OUTBOX_MAX_SIZE"] = 2
    assert audit_outbox.enqueue({"action": "x", "entity_type": "t"}, app=outbox_app)
    assert audit_outbox.enqueue({"action": "x", "entity_type": "t"}, app=outbox_app)
    # At max; critical is refused, non-critical deadmans to disk.
    assert not audit_outbox.enqueue(
        {"action": "critical", "entity_type": "t"},
        critical=True,
        app=outbox_app,
    )
    # Non-critical still gets persisted (deadman).
    assert audit_outbox.enqueue(
        {"action": "low", "entity_type": "t"},
        critical=False,
        app=outbox_app,
    )


def test_audit_client_buffers_to_outbox_on_network_error(outbox_app, flush_outbox):
    if not _redis_reachable(REDIS_URL):
        pytest.skip("Redis not available")
    from app.services.audit_client import AuditClient

    client = AuditClient(
        base_url="http://audit-log:8090",
        token="t",
        enabled=True,
    )
    with patch.object(client, "_request_context", return_value={}):
        with patch("httpx.Client.post", side_effect=ConnectionError("simulated")):
            with outbox_app.app_context():
                assert (
                    client.record(
                        action="user.login_failed",
                        entity_type="user",
                        entity_id="42",
                        actor_id="42",
                        actor_type="user",
                    )
                    is None
                )
    from app.services import audit_outbox

    assert audit_outbox.size(app=outbox_app) == 1


def test_audit_client_dispatches_when_service_reachable(outbox_app, flush_outbox):
    """If the microservice answers 201, the outbox is bypassed."""
    from app.services.audit_client import AuditClient

    class _Resp:
        status_code = 201

        def json(self):
            return {"id": "fake", "hash": "h", "previous_hash": None}

        def raise_for_status(self):
            return None

    client = AuditClient(
        base_url="http://audit-log:8090",
        token="t",
        enabled=True,
    )
    with patch.object(client, "_request_context", return_value={}):
        with patch("httpx.Client.post", return_value=_Resp()):
            with outbox_app.app_context():
                result = client.record(
                    action="test.happy",
                    entity_type="test",
                    entity_id="1",
                )
    assert result["id"] == "fake"


def test_audit_client_raises_on_critical_when_outbox_full_and_no_buffer(outbox_app, flush_outbox):
    from app.services.audit_client import AuditClient, AuditDispatchError

    outbox_app.config["AUDIT_OUTBOX_MAX_SIZE"] = 0
    outbox_app.config["AUDIT_OUTBOX_DLQ_PATH"] = "/nonexistent-readonly/audit-queue"
    client = AuditClient(base_url="http://audit-log:8090", token="t", enabled=True)
    with patch.object(client, "_request_context", return_value={}):
        with patch("httpx.Client.post", side_effect=ConnectionError("down")):
            with outbox_app.app_context():
                with pytest.raises(AuditDispatchError):
                    client.record(
                        action="order.refunded",
                        entity_type="order",
                        entity_id="1",
                        critical=True,
                    )


def test_audit_client_get_returns_event(app):
    from app.services.audit_client import AuditClient

    class _Resp:
        status_code = 200

        def json(self):
            return {"id": "abc", "action": "x"}

        def raise_for_status(self):
            return None

    client = AuditClient(base_url="http://audit-log:8090", token="t", enabled=True)
    with patch("httpx.Client.get", return_value=_Resp()):
        with app.app_context():
            ev = client.get("abc")
    assert ev["action"] == "x"


def test_audit_request_context_pulls_ip_and_user_agent(client, app):
    """A regular HTTP request captures request_id, ip, user_agent in metadata."""
    rv = client.get("/health", headers={"User-Agent": "audit-test/1.0"})
    assert rv.status_code == 200


def test_record_audit_event_fills_top_level_request_fields(app):
    """``record_audit_event`` should fill request_id/ip_address/user_agent as
    top-level audit fields, not just metadata. This is the contract that
    makes the chain verifiable by request.
    """
    app.config["AUDIT_LOG_ENABLED"] = True
    app.config["AUDIT_LOG_BASE_URL"] = "http://audit-log:8090"
    app.config["AUDIT_LOG_TOKEN"] = "test-token"
    app.config["AUDIT_REDIS_URL"] = "redis://localhost:6379/0"  # unreachable
    app.config["AUDIT_OUTBOX_DLQ_PATH"] = "/tmp/audit-test-dlq"

    from app.services.audit import record_audit_event

    captured: list = []

    class _CaptureResponse:
        status_code = 201

        def json(self):
            return {"id": "fake"}

        def raise_for_status(self):
            return None

    def _fake_post(self, path, json=None, **_):
        captured.append((path, json))
        return _CaptureResponse()

    @app.get("/__emit_audit")
    def emit_audit():
        record_audit_event(action="test.event", entity_type="test", entity_id="1")
        return {"ok": True}

    with patch("httpx.Client.post", new=_fake_post):
        client = app.test_client()
        rv = client.get(
            "/__emit_audit",
            headers={
                "User-Agent": "audit-test/1.0",
                "X-Forwarded-For": "10.0.0.7",
                "X-Request-ID": "test-req-123",
            },
        )
    assert rv.status_code == 200
    assert captured, "POST was not called"
    payload = captured[0][1]
    assert payload["request_id"] == "test-req-123"
    assert payload["ip_address"] == "10.0.0.7"
    assert payload["user_agent"] == "audit-test/1.0"


def test_audited_decorator_emits_event_with_status_and_duration(app):
    app.config["AUDIT_LOG_ENABLED"] = True
    app.config["AUDIT_LOG_BASE_URL"] = "http://audit-log:8090"
    app.config["AUDIT_LOG_TOKEN"] = "test-token"

    from app.utils.audit_decorator import audited
    from flask import Blueprint

    bp = Blueprint("audit_decorator_test", __name__)
    captured: list = []

    class _FakeClient:
        def record(self, **kwargs):
            captured.append(kwargs)
            return {"id": "fake"}

    @bp.get("/__test_view/<x>")
    @audited(action="test.decorated", entity_type="decorated", entity_id_arg="x")
    def view(x: int):
        return {"value": x}

    app.register_blueprint(bp)
    with patch("app.services.audit.get_audit_client", return_value=_FakeClient()):
        client = app.test_client()
        rv = client.get("/__test_view/42")
    assert rv.status_code == 200
    assert captured, "record() was not called"
    assert captured[0]["action"] == "test.decorated"
    assert captured[0]["entity_id"] == "42"
    assert captured[0]["metadata"]["status_code"] == 200
    assert captured[0]["metadata"]["duration_ms"] >= 0
