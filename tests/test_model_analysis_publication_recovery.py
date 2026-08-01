from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import (
    AnalysisRunStatus,
    AssetKind,
    Product,
    ProductAnalysisRun,
    ProductModelAsset,
)
from app.services.product_analysis import (
    ACTIVE_ANALYSIS_STATES,
    claim_analysis_run,
    lock_current_analysis_run_for_publish,
    publish_run_results,
    requeue_analysis_run,
    retire_current_gcode_assets,
)
from app.tasks import model_analysis as analysis_task
from app.tasks.model_analysis import (
    _ArtifactPublicationState,
    _artifact_reference_committed,
    _dispatch_completion_side_effects,
    _persist_slicer_artifact,
    _recover_failed_publication,
)


class _ClaimQuery:
    def __init__(self, run, events: list[str]) -> None:
        self.run = run
        self.events = events

    def filter(self, *criteria):
        self.events.append("filter")
        return self

    def populate_existing(self):
        self.events.append("populate_existing")
        return self

    def with_for_update(self):
        self.events.append("with_for_update")
        return self

    def one_or_none(self):
        self.events.append("one_or_none")
        return self.run


class _ClaimSession:
    def __init__(self, run, product) -> None:
        self.run = run
        self.product = product
        self.events: list[str] = []

    def query(self, model):
        self.events.append("query")
        if model is Product:
            return _ClaimQuery(self.product, self.events)
        assert model is ProductAnalysisRun
        return _ClaimQuery(self.run, self.events)

    def get(self, model, identity):
        assert model is Product
        self.events.append(f"get_product:{identity}")
        return self.product

    def add(self, value):
        self.events.append(f"add:{type(value).__name__}")

    def flush(self):
        self.events.append("flush")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


def _run(
    *,
    run_product_id=7,
    status=AnalysisRunStatus.QUEUED,
    is_current=True,
    updated_at=None,
):
    return SimpleNamespace(
        id=19,
        product_id=run_product_id,
        status=status,
        is_current=is_current,
        updated_at=updated_at or datetime.now(timezone.utc),
        completed_at=None,
        error=None,
    )


def test_active_analysis_states_include_conversion_dispatch_phase():
    assert AnalysisRunStatus.CONVERTING in ACTIVE_ANALYSIS_STATES


def test_claim_reclaims_stale_converting_run():
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    stale = _run(
        status=AnalysisRunStatus.CONVERTING,
        updated_at=now - timedelta(minutes=16),
    )
    product = SimpleNamespace(id=7, analysis_status="analyzing")
    session = _ClaimSession(stale, product)

    assert claim_analysis_run(7, 19, session=session, now=now) is stale
    assert stale.status == AnalysisRunStatus.STARTED
    assert stale.updated_at == now
    assert session.events[-1] == "commit"


def test_claim_rejects_fresh_converting_run():
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    active = _run(
        status=AnalysisRunStatus.CONVERTING,
        updated_at=now - timedelta(minutes=14),
    )
    product = SimpleNamespace(id=7, analysis_status="analyzing")
    session = _ClaimSession(active, product)
    assert claim_analysis_run(7, 19, session=session, now=now) is None
    assert session.events[-1] == "rollback"


def test_publish_lock_refuses_to_reopen_terminal_completed_run():
    product = SimpleNamespace(id=7)
    run = _run(status=AnalysisRunStatus.COMPLETE)
    session = _PublishSession(product, run, [run])

    assert lock_current_analysis_run_for_publish(7, 19, session=session) is None


def test_publish_lock_refuses_to_reopen_terminal_failed_run():
    product = SimpleNamespace(id=7)
    run = _run(status=AnalysisRunStatus.FAILED)
    session = _PublishSession(product, run, [run])

    assert lock_current_analysis_run_for_publish(7, 19, session=session) is None


def test_publish_refuses_to_overwrite_current_completed_run():
    product = SimpleNamespace(id=7, analysis_status="complete")
    run = _run(status=AnalysisRunStatus.COMPLETE, is_current=True)

    published = publish_run_results(
        run,
        product,
        parsed_filament_grams=Decimal("999.00"),
        parsed_print_minutes=Decimal("999.00"),
        already_locked=True,
    )

    assert published is False
    assert run.status == AnalysisRunStatus.COMPLETE
    assert product.analysis_status == "complete"


def test_claim_locks_exact_queued_run_and_transitions_once():
    run = _run()
    product = SimpleNamespace(id=7, analysis_status="pending")
    session = _ClaimSession(run, product)

    claimed = claim_analysis_run(7, 19, session=session)

    assert claimed is run
    assert run.status == AnalysisRunStatus.STARTED
    assert product.analysis_status == "analyzing"
    assert session.events == [
        "query",
        "filter",
        "populate_existing",
        "with_for_update",
        "one_or_none",
        "query",
        "filter",
        "populate_existing",
        "with_for_update",
        "one_or_none",
        "add:SimpleNamespace",
        "add:SimpleNamespace",
        "flush",
        "commit",
    ]


def test_claim_rejects_wrong_product_without_mutation():
    run = _run(run_product_id=8)
    product = SimpleNamespace(id=7, analysis_status="pending")
    session = _ClaimSession(run, product)

    assert claim_analysis_run(7, 19, session=session) is None
    assert run.status == AnalysisRunStatus.QUEUED
    assert product.analysis_status == "pending"
    assert session.events[-1] == "rollback"


def test_claim_rejects_duplicate_or_terminal_delivery_without_mutation():
    for status in (
        AnalysisRunStatus.STARTED,
        AnalysisRunStatus.COMPLETE,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.SUPERSEDED,
    ):
        run = _run(status=status)
        product = SimpleNamespace(id=7, analysis_status="pending")
        session = _ClaimSession(run, product)

        assert claim_analysis_run(7, 19, session=session) is None
        assert run.status == status
        assert product.analysis_status == "pending"
        assert session.events[-1] == "rollback"


def test_claim_rejects_noncurrent_queued_run():
    run = _run(is_current=False)
    product = SimpleNamespace(id=7, analysis_status="pending")
    session = _ClaimSession(run, product)

    assert claim_analysis_run(7, 19, session=session) is None
    assert run.status == AnalysisRunStatus.QUEUED
    assert session.events[-1] == "rollback"


@pytest.mark.parametrize("status", sorted(ACTIVE_ANALYSIS_STATES, key=lambda item: item.value))
def test_claim_reclaims_each_stale_active_lease(status):
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    stale = _run(
        status=status,
        updated_at=now - timedelta(minutes=16),
    )
    product = SimpleNamespace(id=7, analysis_status="analyzing")
    session = _ClaimSession(stale, product)

    assert claim_analysis_run(7, 19, session=session, now=now) is stale
    assert stale.status == AnalysisRunStatus.STARTED
    assert stale.updated_at == now
    assert session.events[-1] == "commit"


@pytest.mark.parametrize("status", sorted(ACTIVE_ANALYSIS_STATES, key=lambda item: item.value))
def test_claim_rejects_each_fresh_active_lease(status):
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    active = _run(
        status=status,
        updated_at=now - timedelta(minutes=14),
    )
    product = SimpleNamespace(id=7, analysis_status="analyzing")
    active_session = _ClaimSession(active, product)
    assert claim_analysis_run(7, 19, session=active_session, now=now) is None
    assert active_session.events[-1] == "rollback"


def test_requeue_exact_run_before_retry_but_never_reopens_terminal_runs():
    product = SimpleNamespace(id=7, analysis_status="failed", analysis_error="boom")
    slicing = _run(status=AnalysisRunStatus.SLICING)
    session = _ClaimSession(slicing, product)

    assert requeue_analysis_run(7, 19, session=session) is True
    assert slicing.status == AnalysisRunStatus.QUEUED
    assert slicing.error is None
    assert slicing.completed_at is None
    assert product.analysis_status == "pending"
    assert session.events[-1] == "commit"

    for status in (
        AnalysisRunStatus.COMPLETE,
        AnalysisRunStatus.SUPERSEDED,
        AnalysisRunStatus.FAILED,
    ):
        terminal = _run(status=status)
        terminal_session = _ClaimSession(terminal, product)
        assert requeue_analysis_run(7, 19, session=terminal_session) is False
        assert terminal.status == status
        assert terminal_session.events[-1] == "rollback"


class _RetireQuery:
    def __init__(self) -> None:
        self.updated = None

    def filter(self, *criteria):
        return self

    def update(self, values, synchronize_session=False):
        self.updated = values
        return 1


class _RetireSession:
    def __init__(self) -> None:
        self.query_value = _RetireQuery()
        self.added = []

    def query(self, model):
        return self.query_value

    def add(self, value):
        self.added.append(value)


def test_retain_gcode_false_clears_legacy_pointer_and_stales_only_gcode_query():
    product = SimpleNamespace(id=7, gcode_path="old.gcode")
    session = _RetireSession()

    assert retire_current_gcode_assets(product, session=session) == 1
    assert product.gcode_path is None
    assert session.query_value.updated == {ProductModelAsset.is_current: False}
    assert session.added == [product]


class _PublishQuery:
    def __init__(self, value, events: list[str], label: str) -> None:
        self.value = value
        self.events = events
        self.label = label

    def filter(self, *criteria):
        self.events.append(f"{self.label}:filter")
        return self

    def populate_existing(self):
        self.events.append(f"{self.label}:populate_existing")
        return self

    def with_for_update(self):
        self.events.append(f"{self.label}:with_for_update")
        return self

    def one_or_none(self):
        self.events.append(f"{self.label}:one_or_none")
        return self.value

    def all(self):
        self.events.append(f"{self.label}:all")
        return self.value


class _PublishSession:
    def __init__(self, product, run, current_runs) -> None:
        self.values = [product, run, current_runs]
        self.events: list[str] = []

    def query(self, model):
        label = "product" if model is Product else f"run-{len(self.values)}"
        self.events.append(f"query:{label}")
        return _PublishQuery(self.values.pop(0), self.events, label)


def test_final_publish_locks_product_then_exact_run_and_requires_sole_current_relationship():
    product = SimpleNamespace(id=7)
    run = _run()
    session = _PublishSession(product, run, [run])

    assert lock_current_analysis_run_for_publish(7, 19, session=session) == (product, run)
    assert session.events.index("product:with_for_update") < session.events.index(
        "run-2:with_for_update"
    )
    assert session.events[-1] == "run-1:all"

    competing = _run()
    competing.id = 20
    ambiguous = _PublishSession(product, run, [run, competing])
    assert lock_current_analysis_run_for_publish(7, 19, session=ambiguous) is None


class _RecoverySession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def rollback(self):
        self.events.append("rollback")

    def remove(self):
        self.events.append("remove")


def test_precommit_failure_rolls_back_then_deletes_unique_upload_and_marks_failed():
    events: list[str] = []
    state = _ArtifactPublicationState(storage_reference="s3://products/run-19/artifact.gcode")

    _recover_failed_publication(
        state,
        product_id=7,
        run_id=19,
        original_error=RuntimeError("flush failed"),
        session=_RecoverySession(events),
        delete_reference=lambda reference: events.append(f"delete:{reference}"),
        committed_check=lambda **kwargs: events.append("unexpected-check") or False,
        mark_failed=lambda **kwargs: events.append("mark_failed"),
    )

    assert events == [
        "rollback",
        "delete:s3://products/run-19/artifact.gcode",
        "remove",
        "mark_failed",
    ]


def test_upload_then_asset_flush_failure_is_compensated_from_tracked_reference(tmp_path):
    events: list[str] = []
    artifact_path = tmp_path / "dragon.gcode.3mf"
    artifact_path.write_bytes(b"native")
    product = SimpleNamespace(id=7, slug="dragon", name="Dragon")
    run = SimpleNamespace(id=19)
    result = SimpleNamespace(
        artifact_path=artifact_path,
        artifact_filename="dragon.gcode.3mf",
        artifact_media_type="application/vnd.bambulab.gcode-3mf",
        artifact_size=6,
        artifact_sha256="a" * 64,
        engine_key="bambu",
    )
    state = _ArtifactPublicationState()

    try:
        _persist_slicer_artifact(
            product,
            run,
            result,
            state,
            bucket="products",
            local_root=tmp_path / "stored",
            upload=lambda *args, **kwargs: (
                events.append(f"upload:{kwargs['key']}")
                or "s3://products/products/7/analysis-runs/19/dragon.gcode.3mf"
            ),
            create_asset=lambda *args, **kwargs: (
                events.append("create_asset_flush")
                or (_ for _ in ()).throw(RuntimeError("flush failed"))
            ),
        )
    except RuntimeError as exc:
        _recover_failed_publication(
            state,
            product_id=7,
            run_id=19,
            original_error=exc,
            session=_RecoverySession(events),
            delete_reference=lambda reference: events.append(f"delete:{reference}"),
            committed_check=lambda **kwargs: False,
            mark_failed=lambda **kwargs: events.append("mark_failed"),
        )

    assert events == [
        "upload:products/7/analysis-runs/19/dragon.gcode.3mf",
        "create_asset_flush",
        "rollback",
        "delete:s3://products/products/7/analysis-runs/19/dragon.gcode.3mf",
        "remove",
        "mark_failed",
    ]


def test_create_then_raise_upload_is_compensated_from_planned_reference(tmp_path):
    events: list[str] = []
    artifact_path = tmp_path / "dragon.gcode.3mf"
    artifact_path.write_bytes(b"native")
    product = SimpleNamespace(id=7, slug="dragon", name="Dragon")
    run = SimpleNamespace(id=19)
    result = SimpleNamespace(
        artifact_path=artifact_path,
        artifact_filename="dragon.gcode.3mf",
        artifact_media_type="application/vnd.bambulab.gcode-3mf",
        artifact_size=6,
        artifact_sha256="a" * 64,
        engine_key="bambu",
    )
    state = _ArtifactPublicationState()
    expected = str((tmp_path / "stored/products/7/analysis-runs/19/dragon.gcode.3mf").resolve())

    def create_then_raise(*args, **kwargs):
        destination = tmp_path / "stored" / kwargs["key"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"native")
        events.append(f"created:{destination.resolve()}")
        raise RuntimeError("upload acknowledgement lost")

    try:
        _persist_slicer_artifact(
            product,
            run,
            result,
            state,
            bucket="products",
            local_root=tmp_path / "stored",
            upload=create_then_raise,
            create_asset=lambda *args, **kwargs: events.append("unexpected_asset"),
        )
    except RuntimeError as exc:
        _recover_failed_publication(
            state,
            product_id=7,
            run_id=19,
            original_error=exc,
            session=_RecoverySession(events),
            delete_reference=lambda reference: events.append(f"delete:{reference}"),
            committed_check=lambda **kwargs: False,
            mark_failed=lambda **kwargs: events.append("mark_failed"),
        )

    assert state.storage_reference == expected
    assert events == [
        f"created:{expected}",
        "rollback",
        f"delete:{expected}",
        "remove",
        "mark_failed",
    ]


def test_ambiguous_commit_failure_checks_fresh_state_before_deleting_uncommitted_upload():
    events: list[str] = []
    state = _ArtifactPublicationState(
        storage_reference="s3://products/run-19/artifact.gcode",
        commit_attempted=True,
    )

    _recover_failed_publication(
        state,
        product_id=7,
        run_id=19,
        original_error=RuntimeError("commit connection lost"),
        session=_RecoverySession(events),
        delete_reference=lambda reference: events.append(f"delete:{reference}"),
        committed_check=lambda **kwargs: events.append("fresh_committed_check") or False,
        mark_failed=lambda **kwargs: events.append("mark_failed"),
    )

    assert events == [
        "rollback",
        "remove",
        "fresh_committed_check",
        "delete:s3://products/run-19/artifact.gcode",
        "remove",
        "mark_failed",
    ]


def test_ambiguous_commit_failure_never_deletes_or_fails_committed_current_upload():
    events: list[str] = []
    state = _ArtifactPublicationState(
        storage_reference="s3://products/run-19/artifact.gcode",
        commit_attempted=True,
    )

    _recover_failed_publication(
        state,
        product_id=7,
        run_id=19,
        original_error=RuntimeError("commit acknowledgement lost"),
        session=_RecoverySession(events),
        delete_reference=lambda reference: events.append(f"delete:{reference}"),
        committed_check=lambda **kwargs: events.append("fresh_committed_check") or True,
        mark_failed=lambda **kwargs: events.append("mark_failed"),
    )

    assert events == ["rollback", "remove", "fresh_committed_check"]


class _CommittedAssetSession:
    def __init__(self, run, asset) -> None:
        self.run = run
        self.asset = asset

    def get(self, model, identity):
        if model is ProductAnalysisRun:
            return self.run
        return self.asset


def test_ambiguous_commit_verification_preserves_committed_asset_after_run_superseded():
    asset = SimpleNamespace(
        id=55,
        storage_reference="s3://products/run-19/dragon.gcode.3mf",
        size_bytes=123,
        sha256="a" * 64,
        asset_kind=AssetKind.GCODE,
    )
    run = SimpleNamespace(
        id=19,
        status=AnalysisRunStatus.SUPERSEDED,
        gcode_asset_id=55,
    )

    assert (
        _artifact_reference_committed(
            storage_reference=asset.storage_reference,
            run_id=19,
            artifact_size=123,
            artifact_sha256="a" * 64,
            session=_CommittedAssetSession(run, asset),
        )
        is True
    )


def test_postcommit_conversion_and_audit_failures_are_nonthrowing_and_idempotent():
    events: list[str] = []
    product = SimpleNamespace(
        id=7,
        business_id=3,
        model_convert_to_glb=True,
    )
    slicer_result = SimpleNamespace(
        engine_key="bambu",
        fallback_used=False,
        estimate_only=False,
        artifact_sha256="a" * 64,
    )

    task_id = _dispatch_completion_side_effects(
        product=product,
        slicer_result=slicer_result,
        convert_dispatch=lambda product_id: (
            events.append(f"convert:{product_id}")
            or (_ for _ in ()).throw(RuntimeError("broker unavailable"))
        ),
        audit_record=lambda **kwargs: (
            events.append(kwargs["action"])
            or (_ for _ in ()).throw(RuntimeError("audit unavailable"))
        ),
    )

    assert task_id is None
    assert events == ["convert:7", "model_analysis.completed"]


class _RetrySignal(Exception):
    pass


def test_task_requeues_exact_run_before_requesting_celery_retry(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        analysis_task,
        "claim_analysis_run",
        lambda *args: (_ for _ in ()).throw(RuntimeError("transient")),
    )
    monkeypatch.setattr(
        analysis_task,
        "_recover_failed_publication",
        lambda *args, **kwargs: events.append("recover"),
    )
    monkeypatch.setattr(
        analysis_task,
        "requeue_analysis_run",
        lambda product_id, run_id: events.append(f"requeue:{product_id}:{run_id}") or True,
    )
    monkeypatch.setattr(
        analysis_task,
        "get_audit_client",
        lambda: SimpleNamespace(record=lambda **kwargs: events.append("audit_failed_attempt")),
    )
    monkeypatch.setattr(
        analysis_task.analyze_product_model,
        "retry",
        lambda **kwargs: events.append("retry") or (_ for _ in ()).throw(_RetrySignal()),
    )

    try:
        analysis_task.analyze_product_model.run(7, 19)
    except _RetrySignal:
        pass

    assert events == [
        "recover",
        "audit_failed_attempt",
        "requeue:7:19",
        "retry",
    ]


def test_task_exhausts_bounded_retries_without_reopening_run(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        analysis_task,
        "claim_analysis_run",
        lambda *args: (_ for _ in ()).throw(RuntimeError("persistent")),
    )
    monkeypatch.setattr(
        analysis_task,
        "_recover_failed_publication",
        lambda *args, **kwargs: events.append("recover_terminal"),
    )
    monkeypatch.setattr(
        analysis_task,
        "requeue_analysis_run",
        lambda *args: events.append("unexpected_requeue") or True,
    )
    monkeypatch.setattr(
        analysis_task,
        "get_audit_client",
        lambda: SimpleNamespace(record=lambda **kwargs: events.append("audit_terminal")),
    )

    analysis_task.analyze_product_model.push_request(retries=2)
    try:
        try:
            analysis_task.analyze_product_model.run(7, 19)
        except RuntimeError as exc:
            assert str(exc) == "persistent"
    finally:
        analysis_task.analyze_product_model.pop_request()

    assert events == ["recover_terminal", "audit_terminal"]


def test_duplicate_delivery_exits_before_analysis_side_effects(monkeypatch):
    slice_call = SimpleNamespace(called=False)
    audit_call = SimpleNamespace(called=False)
    monkeypatch.setattr(analysis_task, "claim_analysis_run", lambda *args: None)
    monkeypatch.setattr(
        analysis_task,
        "slice_with_slicer",
        lambda *args, **kwargs: setattr(slice_call, "called", True),
    )
    monkeypatch.setattr(
        analysis_task,
        "_record_analysis_step",
        lambda *args, **kwargs: setattr(audit_call, "called", True),
    )

    result = analysis_task.analyze_product_model.run(7, 19)

    assert result == {
        "success": False,
        "data": {"product_id": 7, "run_id": 19, "idempotent": True},
        "error": "analysis run is not claimable",
    }
    assert slice_call.called is False
    assert audit_call.called is False


def test_studio_enqueues_every_analysis_with_product_and_exact_run_id():
    from app.blueprints.products import studio_routes

    tree = ast.parse(inspect.getsource(studio_routes))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "delay"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "analyze_product_model"
    ]

    assert len(calls) == 2
    assert all(len(call.args) == 2 for call in calls)
    assert all(
        isinstance(call.args[1], ast.Attribute) and call.args[1].attr == "id" for call in calls
    )


def test_file_path_migration_uses_legacy_gcode_namespace():
    from app import cli

    source = inspect.getsource(cli.migrate_file_paths.callback)

    assert "storage_key_fn=legacy_gcode_storage_key" in source
