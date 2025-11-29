"""Git worktree management for parallel task isolation.

This module provides the WorktreeManager class for creating, managing,
and cleaning up Git worktrees. Each task can run in an isolated worktree
on its own branch, preventing Git conflicts during parallel execution.

See docs/dag-execution-design.md for architecture details.
"""

import asyncio
import subprocess
from pathlib import Path


class WorktreeError(Exception):
    """Error during worktree operations."""
    pass


class WorktreeManager:
    """Manages Git worktrees for parallel task execution.

    Usage:
        manager = WorktreeManager()
        path = await manager.create("task_1", "feature/task-1")
        # ... run task in path ...
        await manager.cleanup("task_1")
    """

    def __init__(self, repo_root: str | None = None):
        """Initialize worktree manager.

        Args:
            repo_root: Git repository root. Auto-detected if None.
        """
        if repo_root:
            self.repo_root = Path(repo_root)
        else:
            self.repo_root = self._find_repo_root()
        self.worktree_dir = self.repo_root / ".worktrees"

    def _find_repo_root(self) -> Path:
        """Find git repository root from current directory."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise WorktreeError("Not in a git repository")
        return Path(result.stdout.strip())

    async def _run_git(
        self, *args: str, cwd: Path | None = None
    ) -> tuple[int, str, str]:
        """Run git command asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd or self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(), stderr.decode()

    async def check_repo_state(self) -> list[str]:
        """Check if repo is safe for worktree operations.

        Returns list of warnings/errors. Empty = safe.
        """
        warnings = []

        # Check for uncommitted changes
        code, out, _ = await self._run_git("status", "--porcelain")
        if code == 0 and out.strip():
            warnings.append("Warning: Repository has uncommitted changes")

        # Check for ongoing rebase/merge
        git_dir = self.repo_root / ".git"
        if (git_dir / "MERGE_HEAD").exists():
            warnings.append("Error: Merge in progress")
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            warnings.append("Error: Rebase in progress")

        return warnings

    async def create(
        self, task_id: str, branch: str, base_branch: str = "HEAD"
    ) -> Path:
        """Create a new worktree for a task.

        Args:
            task_id: Unique task identifier (used in path)
            branch: Branch name to create
            base_branch: Base ref for the new branch

        Returns:
            Path to the created worktree

        Raises:
            WorktreeError: If creation fails
        """
        worktree_path = self.worktree_dir / task_id

        # Ensure .worktrees directory exists
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

        # Check if worktree already exists
        if worktree_path.exists():
            raise WorktreeError(f"Worktree path already exists: {worktree_path}")

        # Check if branch already exists
        code, _, _ = await self._run_git(
            "rev-parse", "--verify", f"refs/heads/{branch}"
        )
        if code == 0:
            raise WorktreeError(f"Branch already exists: {branch}")

        # Create worktree with new branch
        code, out, err = await self._run_git(
            "worktree", "add", str(worktree_path), "-b", branch, base_branch
        )
        if code != 0:
            raise WorktreeError(f"Failed to create worktree: {err}")

        return worktree_path

    async def merge_branches(
        self, worktree_path: Path, branches: list[str]
    ) -> bool:
        """Merge branches into a worktree.

        Args:
            worktree_path: Path to the worktree
            branches: Branch names to merge

        Returns:
            True if all merges succeeded
        """
        for branch in branches:
            code, _, err = await self._run_git(
                "merge", branch, "--no-edit",
                cwd=worktree_path
            )
            if code != 0:
                return False
        return True

    async def cleanup(self, task_id: str, force: bool = False) -> None:
        """Remove a worktree.

        Args:
            task_id: Task identifier
            force: Force removal even with uncommitted changes
        """
        worktree_path = self.worktree_dir / task_id

        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")

        code, _, err = await self._run_git(*args)
        if code != 0 and "not a working tree" not in err.lower():
            raise WorktreeError(f"Failed to remove worktree: {err}")

    async def cleanup_all(self, force: bool = False) -> int:
        """Remove all worktrees in .worktrees/ directory.

        Returns:
            Number of worktrees removed
        """
        if not self.worktree_dir.exists():
            return 0

        count = 0
        for child in self.worktree_dir.iterdir():
            if child.is_dir():
                try:
                    await self.cleanup(child.name, force=force)
                    count += 1
                except WorktreeError:
                    pass  # Skip problematic worktrees

        # Remove empty .worktrees directory
        try:
            self.worktree_dir.rmdir()
        except OSError:
            pass  # Directory not empty or other issue

        return count

    async def list_worktrees(self) -> list[dict[str, str]]:
        """List all active worktrees.

        Returns:
            List of dicts with 'path', 'branch', 'commit' keys
        """
        code, out, _ = await self._run_git("worktree", "list", "--porcelain")
        if code != 0:
            return []

        worktrees = []
        current: dict[str, str] = {}

        for line in out.strip().split("\n"):
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["commit"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]

        if current:
            worktrees.append(current)

        return worktrees

    def get_worktree_path(self, task_id: str) -> Path:
        """Get path where worktree would be created."""
        return self.worktree_dir / task_id
