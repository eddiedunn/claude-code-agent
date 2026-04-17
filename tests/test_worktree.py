"""Tests for WorktreeManager."""

import subprocess

import pytest

from grind.worktree import WorktreeError, WorktreeManager


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repository for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo, check=True, capture_output=True
    )

    # Create initial commit (required for worktrees)
    readme = repo / "README.md"
    readme.write_text("# Test Repository\n")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo, check=True, capture_output=True
    )

    return repo


class TestWorktreeManager:
    @pytest.mark.asyncio
    async def test_create_worktree(self, git_repo):
        """Creating a worktree creates directory and branch."""
        manager = WorktreeManager(str(git_repo))

        path = await manager.create("task_1", "feature/task-1")

        assert path.exists()
        assert path == git_repo / ".worktrees" / "task_1"
        assert (path / "README.md").exists()

    @pytest.mark.asyncio
    async def test_create_worktree_already_exists(self, git_repo):
        """Creating worktree twice raises error."""
        manager = WorktreeManager(str(git_repo))

        await manager.create("task_1", "feature/task-1")

        with pytest.raises(WorktreeError, match="already exists"):
            await manager.create("task_1", "feature/task-2")

    @pytest.mark.asyncio
    async def test_create_worktree_branch_exists(self, git_repo):
        """Creating worktree with existing branch raises error."""
        manager = WorktreeManager(str(git_repo))

        # Create branch manually
        subprocess.run(
            ["git", "branch", "existing-branch"],
            cwd=git_repo, check=True, capture_output=True
        )

        with pytest.raises(WorktreeError, match="Branch already exists"):
            await manager.create("task_1", "existing-branch")

    @pytest.mark.asyncio
    async def test_cleanup_worktree(self, git_repo):
        """Cleaning up worktree removes directory."""
        manager = WorktreeManager(str(git_repo))

        path = await manager.create("task_1", "feature/task-1")
        assert path.exists()

        await manager.cleanup("task_1", force=True)
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_merge_branches(self, git_repo):
        """Merging branches brings changes into worktree."""
        manager = WorktreeManager(str(git_repo))

        # Create a branch with a new file
        subprocess.run(
            ["git", "checkout", "-b", "feature-a"],
            cwd=git_repo, check=True, capture_output=True
        )
        (git_repo / "feature_a.txt").write_text("Feature A\n")
        subprocess.run(
            ["git", "add", "."], cwd=git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add feature A"],
            cwd=git_repo, check=True, capture_output=True
        )

        # Go back to main branch (might be master or main)
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=git_repo, check=True, capture_output=True
        )

        # Create worktree and merge
        path = await manager.create("task_b", "feature-b")
        success = await manager.merge_branches(path, ["feature-a"])

        assert success
        assert (path / "feature_a.txt").exists()

    @pytest.mark.asyncio
    async def test_list_worktrees(self, git_repo):
        """Listing worktrees shows all active worktrees."""
        manager = WorktreeManager(str(git_repo))

        await manager.create("task_1", "feature/task-1")
        await manager.create("task_2", "feature/task-2")

        worktrees = await manager.list_worktrees()

        # Should have main worktree + 2 created
        assert len(worktrees) >= 2
        paths = [w.get("path", "") for w in worktrees]
        assert any("task_1" in p for p in paths)
        assert any("task_2" in p for p in paths)

    @pytest.mark.asyncio
    async def test_cleanup_all(self, git_repo):
        """Cleanup all removes all worktrees."""
        manager = WorktreeManager(str(git_repo))

        await manager.create("task_1", "feature/task-1")
        await manager.create("task_2", "feature/task-2")
        await manager.create("task_3", "feature/task-3")

        count = await manager.cleanup_all(force=True)

        assert count == 3
        assert not (git_repo / ".worktrees" / "task_1").exists()
        assert not (git_repo / ".worktrees" / "task_2").exists()
        assert not (git_repo / ".worktrees" / "task_3").exists()

    @pytest.mark.asyncio
    async def test_check_repo_state_clean(self, git_repo):
        """Clean repo has no errors."""
        manager = WorktreeManager(str(git_repo))

        warnings = await manager.check_repo_state()

        # Should have no errors (warnings OK)
        errors = [w for w in warnings if "Error" in w]
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_check_repo_state_uncommitted(self, git_repo):
        """Uncommitted changes trigger warning."""
        manager = WorktreeManager(str(git_repo))

        # Create uncommitted change
        (git_repo / "uncommitted.txt").write_text("uncommitted\n")

        warnings = await manager.check_repo_state()

        assert any("uncommitted" in w.lower() for w in warnings)
