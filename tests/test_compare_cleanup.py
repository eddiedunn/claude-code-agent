"""Tests for compare worktree cleanup behaviour.

All tests use a fake/mocked WorktreeManager — no real git operations.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grind.compare import (
    CompareSession,
    _cleanup_worktree_and_branch,
    _run_one,
)
from grind.models import GrindResult, GrindStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(**kwargs) -> CompareSession:
    defaults = dict(
        task="Fix the bug",
        verify="pytest",
        models=["claude/sonnet"],
        slug="fix-the-bug",
    )
    defaults.update(kwargs)
    return CompareSession(**defaults)


def _make_manager(worktree_path: Path = Path("/tmp/fake/worktree")) -> MagicMock:
    """Return a fake WorktreeManager with async methods."""
    manager = MagicMock()
    manager.create = AsyncMock(return_value=worktree_path)
    manager.cleanup = AsyncMock(return_value=None)
    manager._run_git = AsyncMock(return_value=(0, "", ""))
    return manager


def _make_grind_result(status: GrindStatus, iterations: int = 1) -> GrindResult:
    return GrindResult(
        status=status,
        iterations=iterations,
        duration_seconds=1.0,
        model="claude/sonnet",
    )


# ---------------------------------------------------------------------------
# _cleanup_worktree_and_branch unit tests
# ---------------------------------------------------------------------------

class TestCleanupWorktreeAndBranch:
    @pytest.mark.asyncio
    async def test_calls_cleanup_prune_and_delete(self):
        manager = _make_manager()
        await _cleanup_worktree_and_branch(manager, "task-id", "compare/slug/claude-sonnet")

        manager.cleanup.assert_awaited_once_with("task-id", force=True)
        # _run_git called twice: worktree prune, then branch -D
        assert manager._run_git.await_count == 2
        calls = manager._run_git.await_args_list
        assert calls[0].args == ("worktree", "prune")
        assert calls[1].args == ("branch", "-D", "compare/slug/claude-sonnet")

    @pytest.mark.asyncio
    async def test_swallows_cleanup_error(self):
        manager = _make_manager()
        manager.cleanup.side_effect = RuntimeError("boom")
        # Must not raise
        await _cleanup_worktree_and_branch(manager, "task-id", "some-branch")

    @pytest.mark.asyncio
    async def test_swallows_prune_error(self):
        manager = _make_manager()
        manager._run_git.side_effect = RuntimeError("git error")
        await _cleanup_worktree_and_branch(manager, "task-id", "some-branch")

    @pytest.mark.asyncio
    async def test_continues_after_partial_failure(self):
        """If cleanup raises, prune and branch-delete are still attempted."""
        manager = _make_manager()
        manager.cleanup.side_effect = RuntimeError("cleanup failed")

        # _run_git calls should still happen despite cleanup failing
        await _cleanup_worktree_and_branch(manager, "task-id", "branch")
        assert manager._run_git.await_count == 2


# ---------------------------------------------------------------------------
# _run_one cleanup behaviour
# ---------------------------------------------------------------------------

class TestRunOneCleanup:
    """Verify cleanup is called for every terminal status."""

    def _patch_grind(self, grind_result: GrindResult | None = None, raise_exc: Exception | None = None):
        """Return a context manager that patches grind.engine.grind."""
        if raise_exc is not None:
            mock_coro = AsyncMock(side_effect=raise_exc)
        else:
            mock_coro = AsyncMock(return_value=grind_result)
        return patch("grind.compare.grind", return_value=mock_coro())

    @pytest.mark.asyncio
    async def test_complete_triggers_cleanup(self):
        session = _make_session()
        manager = _make_manager()
        grind_result = _make_grind_result(GrindStatus.COMPLETE)

        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.COMPLETE
        manager.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_triggers_cleanup(self):
        """Regression: ERROR status must trigger cleanup (the original bug)."""
        session = _make_session()
        manager = _make_manager()
        grind_result = _make_grind_result(GrindStatus.ERROR, iterations=0)

        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.ERROR
        manager.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stuck_triggers_cleanup(self):
        session = _make_session()
        manager = _make_manager()
        grind_result = _make_grind_result(GrindStatus.STUCK)

        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.STUCK
        manager.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_in_grind_triggers_cleanup(self):
        """Unexpected exception inside _run_one still runs cleanup (try/finally)."""
        session = _make_session()
        manager = _make_manager()

        with patch("grind.compare.grind", new_callable=AsyncMock, side_effect=RuntimeError("unexpected")):
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.ERROR
        assert "unexpected" in result.error
        manager.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_raising_does_not_propagate(self):
        """If cleanup itself raises, _run_one must not surface the error."""
        session = _make_session()
        manager = _make_manager()
        # Make cleanup raise on every call
        manager.cleanup.side_effect = RuntimeError("cleanup failed")
        grind_result = _make_grind_result(GrindStatus.ERROR, iterations=0)

        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            # Must not raise
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.ERROR

    @pytest.mark.asyncio
    async def test_timeout_triggers_cleanup(self):
        """TimeoutError (asyncio.TimeoutError) still triggers cleanup."""
        session = _make_session(timeout=0.001)
        manager = _make_manager()

        async def _slow():
            await asyncio.sleep(10)
            return _make_grind_result(GrindStatus.COMPLETE)

        with patch("grind.compare.grind", new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
            result = await _run_one(session, "claude/sonnet", manager)

        assert result.status is None  # timeout sentinel
        manager.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_worktree_create_failure_skips_cleanup(self):
        """If worktree creation fails, cleanup should NOT be called (nothing to clean)."""
        session = _make_session()
        manager = _make_manager()
        manager.create.side_effect = RuntimeError("worktree create failed")

        result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.ERROR
        assert "worktree create failed" in result.error.lower() or "Worktree setup failed" in result.error
        manager.cleanup.assert_not_awaited()


# ---------------------------------------------------------------------------
# Idempotent re-run simulation
# ---------------------------------------------------------------------------

class TestIdempotentRerun:
    """Simulate running _run_one twice with the same task/model.

    On the second call, `manager.create` would normally raise
    "Branch already exists" — but because the first run cleaned up (branch
    deleted), the second create should succeed.

    We verify that after a first run the mock cleanup is called, so a second
    call to create with a fresh manager is not blocked.
    """

    @pytest.mark.asyncio
    async def test_second_run_not_blocked_after_first_cleanup(self):
        """After first _run_one cleans up, a second call succeeds."""
        session = _make_session()
        grind_result = _make_grind_result(GrindStatus.ERROR, iterations=0)

        # First run
        manager1 = _make_manager()
        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            result1 = await _run_one(session, "claude/sonnet", manager1)

        assert result1.status == GrindStatus.ERROR
        # Cleanup was called — branch is now deleted in the real world
        manager1.cleanup.assert_awaited_once()

        # Second run — fresh manager (branch is gone, create succeeds)
        manager2 = _make_manager()
        with patch("grind.compare.grind", new_callable=AsyncMock, return_value=grind_result):
            result2 = await _run_one(session, "claude/sonnet", manager2)

        assert result2.status == GrindStatus.ERROR
        manager2.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_branch_already_exists_on_create_returns_error(self):
        """If branch already exists (stale state), _run_one returns ERROR gracefully."""
        from grind.worktree import WorktreeError

        session = _make_session()
        manager = _make_manager()
        manager.create.side_effect = WorktreeError("Branch already exists: compare/fix-the-bug/claude-sonnet")

        result = await _run_one(session, "claude/sonnet", manager)

        assert result.status == GrindStatus.ERROR
        assert "Branch already exists" in result.error
        # No cleanup since worktree was never created
        manager.cleanup.assert_not_awaited()
