from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

from app.models import AnalysisRunStatus, Product, ProductAnalysisRun
from app.services.product_analysis import claim_analysis_run
from app.tasks import model_analysis as analysis_task
from app.tasks.model_analysis import (
    _ArtifactPublicationState,
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
        assert model is ProductAnalysisRun
        self.events.append("query")
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


def _run(*, run_product_id=7, status=AnalysisRunStatus.QUEUED, is_current=True):
    return SimpleNamespace(
        id=19,
        product_id=run_product_id,
        status=status,
        is_current=is_current,
    )


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
        "get_product:7",
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
