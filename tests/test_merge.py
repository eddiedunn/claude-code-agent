"""Tests for GrindMerger."""

import subprocess

import pytest

from grind.merge import GrindMerger, MergeError, MergeSession


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repository for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

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


@pytest.fixture
def git_repo_with_branches(git_repo):
    """Create repo with multiple feature branches."""
    file1 = git_repo / "file1.txt"
    file2 = git_repo / "file2.txt"

    subprocess.run(
        ["git", "checkout", "-b", "fix/branch-1"],
        cwd=git_repo, check=True, capture_output=True
    )
    file1.write_text("Change from branch-1\n")
    subprocess.run(
        ["git", "add", "."], cwd=git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Change in branch-1"],
        cwd=git_repo, check=True, capture_output=True
    )

    subprocess.run(
        ["git", "checkout", "main"],
        cwd=git_repo, check=True, capture_output=True
    )

    subprocess.run(
        ["git", "checkout", "-b", "fix/branch-2"],
        cwd=git_repo, check=True, capture_output=True
    )
    file2.write_text("Change from branch-2\n")
    subprocess.run(
        ["git", "add", "."], cwd=git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Change in branch-2"],
        cwd=git_repo, check=True, capture_output=True
    )

    subprocess.run(
        ["git", "checkout", "main"],
        cwd=git_repo, check=True, capture_output=True
    )

    return git_repo


class TestGrindMerger:
    def test_init_in_git_repo(self, git_repo):
        """GrindMerger can initialize in a git repository."""
        merger = GrindMerger(str(git_repo))
        assert merger.repo_root == git_repo

    def test_init_outside_git_repo(self, tmp_path):
        """GrindMerger raises error outside git repository."""
        non_repo = tmp_path / "non_repo"
        non_repo.mkdir()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(non_repo)
            with pytest.raises(MergeError, match="Not in a git repository"):
                GrindMerger()
        finally:
            os.chdir(old_cwd)

    def test_find_branches_with_pattern(self, git_repo_with_branches):
        """find_branches discovers branches matching pattern."""
        merger = GrindMerger(str(git_repo_with_branches))
        branches = merger.find_branches("fix/*")

        assert "fix/branch-1" in branches
        assert "fix/branch-2" in branches
        assert "main" not in branches

    def test_find_branches_multiple_patterns(self, git_repo_with_branches):
        """find_branches supports comma-separated patterns."""
        subprocess.run(
            ["git", "checkout", "-b", "grind/task-1"],
            cwd=git_repo_with_branches, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=git_repo_with_branches, check=True, capture_output=True
        )

        merger = GrindMerger(str(git_repo_with_branches))
        branches = merger.find_branches("fix/*,grind/*")

        assert "fix/branch-1" in branches
        assert "fix/branch-2" in branches
        assert "grind/task-1" in branches
        assert "main" not in branches

    def test_find_branches_no_matches(self, git_repo):
        """find_branches returns empty list when no matches."""
        merger = GrindMerger(str(git_repo))
        branches = merger.find_branches("nonexistent/*")

        assert branches == []

    @pytest.mark.asyncio
    async def test_merge_branches_clean(self, git_repo_with_branches):
        """merge_branches handles clean merges automatically."""
        merger = GrindMerger(str(git_repo_with_branches))

        session = await merger.merge_branches(
            branches=["fix/branch-1", "fix/branch-2"],
            target="main",
            interactive=False,
        )

        assert session.success_count == 2
        assert session.conflict_count == 0
        assert session.skipped_count == 0
        assert not session.aborted
        assert session.target_branch == "main"
        assert session.staging_branch.startswith("grind-merge-")
        assert session.backup_branch.startswith("grind-backup-")

        result = subprocess.run(
            ["git", "branch", "--list", session.staging_branch],
            cwd=git_repo_with_branches,
            capture_output=True,
            text=True,
        )
        assert session.staging_branch in result.stdout

    @pytest.mark.asyncio
    async def test_merge_creates_backup_branch(self, git_repo_with_branches):
        """merge_branches creates backup branch before merging."""
        merger = GrindMerger(str(git_repo_with_branches))

        session = await merger.merge_branches(
            branches=["fix/branch-1"],
            target="main",
            interactive=False,
        )

        result = subprocess.run(
            ["git", "branch", "--list", session.backup_branch],
            cwd=git_repo_with_branches,
            capture_output=True,
            text=True,
        )
        assert session.backup_branch in result.stdout

    @pytest.mark.asyncio
    async def test_merge_nonexistent_branch(self, git_repo):
        """merge_branches skips nonexistent branches."""
        merger = GrindMerger(str(git_repo))

        session = await merger.merge_branches(
            branches=["nonexistent"],
            target="main",
            interactive=False,
        )

        assert session.success_count == 0

    @pytest.mark.asyncio
    async def test_merge_with_verification_pass(self, git_repo_with_branches):
        """merge_branches runs verification command and tracks result."""
        merger = GrindMerger(str(git_repo_with_branches))

        session = await merger.merge_branches(
            branches=["fix/branch-1"],
            target="main",
            verify_command="echo 'test passed'",
            interactive=False,
        )

        assert session.verification_passed is True
        assert session.verification_command == "echo 'test passed'"

    @pytest.mark.asyncio
    async def test_merge_with_verification_fail(self, git_repo_with_branches):
        """merge_branches detects verification failures."""
        merger = GrindMerger(str(git_repo_with_branches))

        session = await merger.merge_branches(
            branches=["fix/branch-1"],
            target="main",
            verify_command="exit 1",
            interactive=False,
        )

        assert session.verification_passed is False

    @pytest.mark.asyncio
    async def test_merge_no_branches_raises_error(self, git_repo):
        """merge_branches raises error when no branches provided."""
        merger = GrindMerger(str(git_repo))

        with pytest.raises(MergeError, match="No branches to merge"):
            await merger.merge_branches(branches=[], target="main")

    @pytest.mark.asyncio
    async def test_merge_session_properties(self, git_repo_with_branches):
        """MergeSession properties calculate correctly."""
        merger = GrindMerger(str(git_repo_with_branches))

        session = await merger.merge_branches(
            branches=["fix/branch-1", "fix/branch-2"],
            target="main",
            interactive=False,
        )

        assert session.success_count == 2
        assert session.conflict_count == 0
        assert session.skipped_count == 0
        assert session.skipped_branches == []


class TestMergeSession:
    def test_merge_session_properties_empty(self):
        """MergeSession properties work with empty attempts."""
        session = MergeSession(
            target_branch="main",
            staging_branch="grind-merge-123",
            backup_branch="grind-backup-123",
        )

        assert session.success_count == 0
        assert session.conflict_count == 0
        assert session.skipped_count == 0
        assert session.skipped_branches == []
