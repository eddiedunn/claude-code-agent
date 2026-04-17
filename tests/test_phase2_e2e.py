"""End-to-end tests for Phase 2: Worktrees as file-backed state.

Run with: uv run python -m pytest tests/test_phase2_e2e.py -v
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirror Phase 1 style)
# ---------------------------------------------------------------------------

def _wait_for_server(url: str, timeout: int = 15) -> bool:
    """Wait for server to be ready."""
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def _get_json(url: str) -> dict:  # type: ignore[type-arg]
    """GET a JSON endpoint."""
    return json.loads(urllib.request.urlopen(url).read())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def observer_server() -> Generator[str, None, None]:
    """Start the observer server on port 18424 for the test module."""
    base = "http://127.0.0.1:18424"
    db = "/tmp/test_phase2_e2e.db"

    # Clean up any leftover DB files
    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    # fix #11: use same grind_bin pattern as test_phase1_e2e.py for consistency
    # (grind observe is a CLI entry point, not a module — keep the installed-bin approach)
    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18424", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start on port 18424")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)


@pytest.fixture(scope="module")
def git_repo(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    """Create a temporary git repo with an initial commit on main."""
    repo: Path = tmp_path_factory.mktemp("repo")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    yield repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_spawn_creates_state_dir(
    git_repo: Path, observer_server: str
) -> None:
    """Spawning a worktree creates state/ dir and a valid manifest.json."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("spawn-state-test", "grind/spawn-state-test")
    )

    state_dir = worktree_path / "state"
    manifest_path = state_dir / "manifest.json"

    assert state_dir.is_dir(), "state/ directory was not created"
    assert manifest_path.is_file(), "state/manifest.json was not created"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["task_id"] == "spawn-state-test"
    assert manifest["status"] == "active"
    assert "created_at" in manifest

    # Cleanup
    asyncio.run(mgr.cleanup("spawn-state-test", force=True))


# fix #5: test_spawn_emits_event is now self-contained (no implicit ordering dependency)
def test_spawn_emits_event(git_repo: Path, observer_server: str) -> None:
    """Spawning a worktree emits a worktree_spawn event to the observer."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    asyncio.run(mgr.create("emit-event-test", "grind/emit-event-test"))

    events = _get_json(f"{observer_server}/events?event_type=worktree_spawn")
    session_ids = [e["session_id"] for e in events["events"]]
    assert "emit-event-test" in session_ids

    asyncio.run(mgr.cleanup("emit-event-test", force=True))


def test_observer_full_trace(observer_server: str) -> None:
    """Observer DB contains spawn and teardown events from the module's tests."""
    spawn_events = _get_json(
        f"{observer_server}/events?event_type=worktree_spawn"
    )
    teardown_events = _get_json(
        f"{observer_server}/events?event_type=worktree_teardown"
    )

    assert spawn_events["count"] >= 1, (
        f"No worktree_spawn events found: {spawn_events}"
    )
    assert teardown_events["count"] >= 1, (
        f"No worktree_teardown events found: {teardown_events}"
    )


def test_worktree_module_imports() -> None:
    """Worktree module exports expected symbols."""
    from grind.worktree import (  # noqa: F401
        WorktreeError,
        WorktreeManager,
    )

    assert callable(WorktreeManager)
    assert issubclass(WorktreeError, Exception)


# ---------------------------------------------------------------------------
# Error-path and edge-case tests (no observer needed)
# ---------------------------------------------------------------------------

def test_create_raises_if_path_exists(git_repo: Path) -> None:
    """create() raises WorktreeError when the worktree path already exists."""
    from grind.worktree import WorktreeError, WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    asyncio.run(mgr.create("dup-path-test", "grind/dup-path-test"))
    try:
        with pytest.raises(WorktreeError, match="already exists"):
            asyncio.run(mgr.create("dup-path-test", "grind/dup-path-test-2"))
    finally:
        asyncio.run(mgr.cleanup("dup-path-test", force=True))


def test_create_raises_if_branch_exists(git_repo: Path) -> None:
    """create() raises WorktreeError when the branch already exists."""
    from grind.worktree import WorktreeError, WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    asyncio.run(mgr.create("branch-exists-seed", "grind/branch-exists-seed"))
    try:
        # Different path, same branch name — branch already exists
        with pytest.raises(WorktreeError, match="Branch already exists"):
            asyncio.run(
                mgr.create("branch-exists-other", "grind/branch-exists-seed")
            )
    finally:
        asyncio.run(mgr.cleanup("branch-exists-seed", force=True))


def test_check_repo_state_clean(git_repo: Path) -> None:
    """check_repo_state returns an empty list on a clean repo."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    warnings = asyncio.run(mgr.check_repo_state())
    assert warnings == [], f"Expected no warnings on clean repo, got: {warnings}"


def test_check_repo_state_uncommitted(git_repo: Path) -> None:
    """check_repo_state warns about uncommitted changes."""
    from grind.worktree import WorktreeManager

    dirty_file = git_repo / "dirty.txt"
    dirty_file.write_text("uncommitted\n")
    try:
        mgr = WorktreeManager(repo_root=str(git_repo))
        warnings = asyncio.run(mgr.check_repo_state())
        assert any("uncommitted" in w.lower() for w in warnings), (
            f"Expected uncommitted-changes warning, got: {warnings}"
        )
    finally:
        dirty_file.unlink(missing_ok=True)


def test_list_worktrees_includes_main(git_repo: Path) -> None:
    """list_worktrees always returns at least the main worktree entry."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    wts = asyncio.run(mgr.list_worktrees())
    paths = [wt.get("path") for wt in wts]
    assert str(git_repo) in paths, (
        f"Main repo path not found in worktree list: {paths}"
    )


def test_cleanup_all_returns_count(git_repo: Path) -> None:
    """cleanup_all removes all worktrees and returns the correct count."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    asyncio.run(mgr.create("ca-task-0", "grind/ca-task-0"))
    asyncio.run(mgr.create("ca-task-1", "grind/ca-task-1"))
    count = asyncio.run(mgr.cleanup_all(force=True))
    assert count == 2, f"Expected cleanup_all to remove 2 worktrees, got {count}"
    assert not mgr.worktree_dir.exists(), ".worktrees/ should be removed when empty"


def test_cleanup_all_no_worktrees_dir(git_repo: Path) -> None:
    """cleanup_all returns 0 when .worktrees/ does not exist."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    # Ensure .worktrees dir is absent (previous test removed it, but be explicit)
    import shutil
    if mgr.worktree_dir.exists():
        shutil.rmtree(mgr.worktree_dir)
    count = asyncio.run(mgr.cleanup_all())
    assert count == 0


def test_merge_branches_returns_true_on_success(git_repo: Path) -> None:
    """merge_branches returns True when all branches merge cleanly."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    wt_path = asyncio.run(mgr.create("mb-task", "grind/mb-task"))
    # Write and commit a file on the candidate branch
    (wt_path / "mb_output.txt").write_text("merge test\n")
    subprocess.run(["git", "add", "."], cwd=wt_path, check=True)
    subprocess.run(["git", "commit", "-m", "mb commit"], cwd=wt_path, check=True)
    try:
        result = asyncio.run(mgr.merge_branches(git_repo, ["grind/mb-task"]))
        assert result is True
    finally:
        # Undo the merge on main so we don't pollute the shared repo state
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=git_repo, check=True)
        asyncio.run(mgr.cleanup("mb-task", force=True))


# ---------------------------------------------------------------------------
# Mock-based fault-injection tests (no observer needed)
# ---------------------------------------------------------------------------

def test_accept_raises_if_worktree_not_found(git_repo: Path) -> None:
    """accept() raises WorktreeError if task_id is not a known worktree."""
    from grind.worktree import WorktreeError, WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    with pytest.raises(WorktreeError):
        asyncio.run(mgr.accept("nonexistent-task"))


def test_accept_raises_on_detached_head(git_repo: Path) -> None:
    """accept() raises WorktreeError when worktree is in detached HEAD state."""
    from unittest.mock import AsyncMock, patch

    from grind.worktree import WorktreeError, WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    # Create the worktree so get_worktree_path returns a real path
    asyncio.run(mgr.create("detached-test", "grind/detached-test"))

    fake_worktrees = [{
        "path": str(mgr.get_worktree_path("detached-test")),
        "commit": "abc1234",
        # no "branch" key — simulates detached HEAD
    }]

    with patch.object(mgr, "list_worktrees", new=AsyncMock(return_value=fake_worktrees)):
        with pytest.raises(WorktreeError, match="detached"):
            asyncio.run(mgr.accept("detached-test"))

    # Cleanup
    asyncio.run(mgr.cleanup("detached-test", force=True))


# ---------------------------------------------------------------------------
# Git-state-based tests (real fixture manipulation, no observer needed)
# ---------------------------------------------------------------------------

def test_merge_branches_returns_false_on_conflict(git_repo: Path) -> None:
    """merge_branches() returns False when branches have conflicting edits."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))

    # Create two branches that both edit the same line of the same file
    wt_a = asyncio.run(mgr.create("conflict-a", "grind/conflict-a"))
    wt_b = asyncio.run(mgr.create("conflict-b", "grind/conflict-b"))

    conflict_file_a = wt_a / "conflict.txt"
    conflict_file_a.write_text("branch A content\n", encoding="utf-8")
    subprocess.run(["git", "add", "conflict.txt"], cwd=wt_a, check=True)
    subprocess.run(["git", "commit", "-m", "branch A edit"], cwd=wt_a, check=True)

    conflict_file_b = wt_b / "conflict.txt"
    conflict_file_b.write_text("branch B content\n", encoding="utf-8")
    subprocess.run(["git", "add", "conflict.txt"], cwd=wt_b, check=True)
    subprocess.run(["git", "commit", "-m", "branch B edit"], cwd=wt_b, check=True)

    # Create a third worktree on main to run the merge in
    wt_merge = asyncio.run(mgr.create("merge-target", "grind/merge-target"))

    # First merge A — should succeed
    result_a = asyncio.run(mgr.merge_branches(wt_merge, ["grind/conflict-a"]))
    assert result_a is True

    # Now merge B — conflicts with A
    result_b = asyncio.run(mgr.merge_branches(wt_merge, ["grind/conflict-b"]))
    assert result_b is False

    # Cleanup (force=True handles the conflicted/dirty state)
    asyncio.run(mgr.cleanup("conflict-a", force=True))
    asyncio.run(mgr.cleanup("conflict-b", force=True))
    asyncio.run(mgr.cleanup("merge-target", force=True))


def test_accept_non_ff_merge(git_repo: Path) -> None:
    """accept() falls back to non-ff merge when ff is not possible."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))

    # Create candidate worktree
    wt = asyncio.run(mgr.create("non-ff-candidate", "grind/non-ff-candidate"))

    # Commit on the candidate
    (wt / "state" / "non_ff_output.txt").write_text("non-ff result\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "candidate work"], cwd=wt, check=True)

    # Now make main diverge: commit something else directly on main
    # git_repo IS the main worktree, so we can commit there directly
    (git_repo / "main_extra.txt").write_text("extra commit on main\n", encoding="utf-8")
    subprocess.run(["git", "add", "main_extra.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "extra on main"], cwd=git_repo, check=True)

    # Now accept: ff is impossible, must use non-ff merge
    asyncio.run(mgr.accept("non-ff-candidate", target_branch="main"))

    # Candidate's file should be on main
    assert (git_repo / "state" / "non_ff_output.txt").is_file()


def test_check_repo_state_merge_in_progress(git_repo: Path) -> None:
    """check_repo_state() warns when a merge is in progress."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    merge_head = git_repo / ".git" / "MERGE_HEAD"
    merge_head.write_text("0000000000000000000000000000000000000000\n", encoding="utf-8")
    try:
        warnings = asyncio.run(mgr.check_repo_state())
        assert any("Merge" in w for w in warnings), (
            f"Expected merge-in-progress warning, got: {warnings}"
        )
    finally:
        merge_head.unlink()


def test_check_repo_state_rebase_in_progress(git_repo: Path) -> None:
    """check_repo_state() warns when a rebase is in progress."""
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo))
    rebase_dir = git_repo / ".git" / "rebase-merge"
    rebase_dir.mkdir()
    try:
        warnings = asyncio.run(mgr.check_repo_state())
        assert any("Rebase" in w for w in warnings), (
            f"Expected rebase-in-progress warning, got: {warnings}"
        )
    finally:
        rebase_dir.rmdir()
