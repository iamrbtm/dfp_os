from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.api.dependencies import WorkspaceCleanupManager


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_cleanup_manager_strongly_tracks_failures_until_retry_succeeds(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    attempts = 0

    def remove(path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise OSError(f"private failure for {path}")
        path.rmdir()

    manager = WorkspaceCleanupManager(
        remove=remove,
        initial_delay_seconds=0.005,
        max_delay_seconds=0.01,
        shutdown_timeout_seconds=0.2,
    )

    await manager.cleanup(workspace)
    assert manager.pending_count == 1
    assert workspace.exists()

    await _wait_until(lambda: manager.pending_count == 0)

    assert attempts == 4
    assert not workspace.exists()
    await manager.shutdown()


async def test_cleanup_manager_shutdown_drains_retry_that_can_succeed(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    attempts = 0

    def remove(path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("transient")
        path.rmdir()

    manager = WorkspaceCleanupManager(
        remove=remove,
        initial_delay_seconds=5,
        max_delay_seconds=5,
        shutdown_timeout_seconds=0.2,
    )
    await manager.cleanup(workspace)
    assert manager.pending_count == 1

    await manager.shutdown()

    assert attempts >= 2
    assert manager.pending_count == 0
    assert not workspace.exists()


async def test_cleanup_manager_persistent_failure_shutdown_is_bounded_and_sanitized(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    workspace = tmp_path / "private-customer-workspace"
    workspace.mkdir()

    def remove(path: Path) -> None:
        raise OSError(f"cannot remove {path}")

    manager = WorkspaceCleanupManager(
        remove=remove,
        initial_delay_seconds=0.005,
        max_delay_seconds=0.01,
        shutdown_timeout_seconds=0.05,
    )
    with caplog.at_level("WARNING"):
        await manager.cleanup(workspace)
        async with asyncio.timeout(0.25):
            await manager.shutdown()

    assert manager.pending_count == 0
    assert workspace.exists()
    assert "cleanup could not finish during shutdown" in caplog.text.lower()
    assert str(workspace) not in caplog.text
