"""Git worktree management for parallel task isolation.

This module provides the WorktreeManager class for creating, managing,
and cleaning up Git worktrees. Each task can run in an isolated worktree
on its own branch, preventing Git conflicts during parallel execution.

Phase 2 adds file-backed state: every worktree has a `state/` subtree
that agents read/write.  The best-of-N merge API (spawn_pool / accept_from_pool)
lets N candidate worktrees race; only the accepted one folds to main.

See docs/dag-execution-design.md for architecture details.
"""

import asyncio
import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from grind.observer.models import EventType


class WorktreeError(Exception):
    """Error during worktree operations."""
    pass


@dataclass
class WorktreePool:
    """A set of candidate worktrees for one logical task.

    Used by spawn_pool / accept_from_pool to implement best-of-N merge:
    spawn N candidates, pick the winner, tear down the rest.
    """
    task_id: str
    candidates: list[str]  # list of candidate task_ids  # fix #9: renamed from worktrees
    accepted: str | None = None


class WorktreeManager:
    """Manages Git worktrees for parallel task execution.

    Usage:
        manager = WorktreeManager()
        path = await manager.create("task_1", "feature/task-1")
        # ... run task in path ...
        await manager.cleanup("task_1")

    Phase 2 additions:
        - Every created worktree gets a ``state/`` directory with a
          ``state/manifest.json`` tracking lifecycle status.
        - ``observer_url`` enables optional event emission to the
          observer server (never blocks worktree ops if unavailable).
        - ``accept()`` merges one worktree to a target branch.
        - ``spawn_pool()`` / ``accept_from_pool()`` implement best-of-N.
    """

    def __init__(
        self,
        repo_root: str | None = None,
        observer_url: str | None = None,
    ) -> None:
        """Initialize worktree manager.

        Args:
            repo_root: Git repository root. Auto-detected if None.
            observer_url: Base URL of the observer server, e.g.
                ``http://127.0.0.1:18424``.  Events are fire-and-forget;
                a missing or slow observer never blocks worktree ops.
        """
        if repo_root:
            self.repo_root = Path(repo_root)
        else:
            self.repo_root = self._find_repo_root()
        self.worktree_dir = self.repo_root / ".worktrees"
        self.observer_url = observer_url

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
        returncode: int = proc.returncode if proc.returncode is not None else -1
        return returncode, stdout.decode(), stderr.decode()

    async def _emit_event(  # fix #3: now async, uses run_in_executor
        self,
        event_type: str,
        worktree_id: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Fire-and-forget event emission to the observer server.

        Args:
            event_type: One of the ``worktree_*`` EventType string values.
            worktree_id: Used as both ``session_id`` and ``agent_name``.
            extra: Additional top-level fields merged into the payload.
        """
        if not self.observer_url:
            return
        payload: dict[str, object] = {
            "event_type": event_type,
            "session_id": worktree_id,
            "agent_name": worktree_id,
            "timestamp": time.time(),
            **(extra or {}),
        }

        def _post() -> None:
            try:
                req = urllib.request.Request(
                    f"{self.observer_url}/events",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass  # observer is optional — never block worktree ops

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _post)

    async def check_repo_state(self) -> list[str]:
        """Check if repo is safe for worktree operations.

        Returns list of warnings/errors. Empty = safe.
        """
        warnings: list[str] = []

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

        Initialises a ``state/`` directory inside the worktree and writes
        ``state/manifest.json`` recording task metadata and lifecycle status.
        Emits a ``worktree_spawn`` event to the observer if configured.

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

        # Initialise state/ directory
        state_dir = worktree_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        # fix #7: removed redundant worktree_id field; only task_id is stored
        manifest = {
            "task_id": task_id,
            "created_at": time.time(),
            "status": "active",
        }
        (state_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Emit spawn event; fix #8: use EventType enum value
        await self._emit_event(
            EventType.WORKTREE_SPAWN.value,
            task_id,
            {"tool_name": "worktree_spawn", "tool_input": str(worktree_path)},
        )

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

        Updates ``state/manifest.json`` to ``"torn_down"`` before removal and
        emits a ``worktree_teardown`` event.  Also deletes the associated
        branch after the worktree is removed.

        Args:
            task_id: Task identifier
            force: Force removal even with uncommitted changes
        """
        worktree_path = self.worktree_dir / task_id
        manifest_path = worktree_path / "state" / "manifest.json"

        # Retrieve branch name before we destroy the worktree
        branch_name: str | None = None
        worktrees = await self.list_worktrees()
        for wt in worktrees:
            if wt.get("path") == str(worktree_path):
                raw = wt.get("branch", "")
                # branch refs look like "refs/heads/grind/foo" — strip prefix
                branch_name = raw.removeprefix("refs/heads/")
                break

        # Update manifest status before removal
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                data["status"] = "torn_down"
                manifest_path.write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
            except Exception:
                pass  # best-effort

        # Emit teardown event before removal (path still exists); fix #8: use EventType enum value
        await self._emit_event(EventType.WORKTREE_TEARDOWN.value, task_id)

        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")

        code, _, err = await self._run_git(*args)
        if code != 0 and "not a working tree" not in err.lower():
            raise WorktreeError(f"Failed to remove worktree: {err}")

        # Delete the branch (ignore errors — branch may not exist)
        if branch_name:
            await self._run_git("branch", "-D", branch_name)

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

        worktrees: list[dict[str, str]] = []
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

    async def accept(self, task_id: str, target_branch: str = "main") -> None:
        """Merge one worktree's branch to target_branch and emit ACCEPTED event.

        This is the acceptance gate for best-of-N: one worktree wins,
        its changes fold to main, then it's torn down.

        Steps:
        1. Resolve the worktree's branch via ``git worktree list --porcelain``.
        2. Update ``state/manifest.json`` status to ``"accepted"``.
        3. Advance target_branch ref via ``git update-ref`` (fast-forward)
           or ``git merge-tree`` + ``git commit-tree`` + ``git update-ref``
           (non-ff) — never runs ``git checkout`` on the main worktree (fix #1).
        4. Sync main worktree working tree with ``git reset --hard HEAD``.
        5. Emit ``worktree_accepted`` event.
        6. Tear down the worktree.

        Args:
            task_id: Task identifier of the worktree to accept.
            target_branch: Branch that receives the merge (default ``main``).

        Raises:
            WorktreeError: If the worktree is not found or merge fails.
        """
        worktree_path = self.worktree_dir / task_id

        # Resolve branch name
        branch_name: str | None = None
        worktrees = await self.list_worktrees()
        for wt in worktrees:
            if wt.get("path") == str(worktree_path):
                raw = wt.get("branch", "")
                branch_name = raw.removeprefix("refs/heads/")
                break

        if branch_name is None:
            raise WorktreeError(
                f"Worktree not found for task_id={task_id!r} at {worktree_path}"
            )

        # fix #6: guard against detached HEAD state
        if not branch_name:
            raise WorktreeError(
                f"Worktree '{task_id}' is in detached HEAD state — cannot accept"
            )

        # Update manifest to accepted
        manifest_path = worktree_path / "state" / "manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                data["status"] = "accepted"
                manifest_path.write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
            except Exception:
                pass  # best-effort

        # fix #1: merge without touching main worktree HEAD.
        # git worktree add refuses to create a second worktree for an already-checked-out
        # branch, so instead we advance the ref directly using git primitives and then
        # sync the working tree with `git reset --hard HEAD`.
        _, target_sha, _ = await self._run_git(
            "rev-parse", f"refs/heads/{target_branch}"
        )
        target_sha = target_sha.strip()
        _, candidate_sha, _ = await self._run_git("rev-parse", "HEAD", cwd=worktree_path)
        candidate_sha = candidate_sha.strip()

        # Try fast-forward first: target must be an ancestor of candidate
        ff_code, _, _ = await self._run_git(
            "merge-base", "--is-ancestor", target_sha, candidate_sha
        )
        if ff_code == 0:
            # Fast-forward: just advance the ref
            code, _, err = await self._run_git(
                "update-ref", f"refs/heads/{target_branch}", candidate_sha, target_sha
            )
            if code != 0:
                raise WorktreeError(
                    f"Failed to fast-forward {target_branch} to {branch_name}: {err}"
                )
        else:
            # Non-fast-forward: build a merge commit without touching any working tree
            code, merge_tree_sha, err = await self._run_git(
                "merge-tree", "--write-tree", target_sha, candidate_sha
            )
            if code != 0:
                raise WorktreeError(
                    f"Failed to merge {branch_name} into {target_branch} "
                    f"(merge-tree conflict): {err}"
                )
            merge_tree_sha = merge_tree_sha.strip()
            merge_msg = f"Merge branch '{branch_name}' into {target_branch}"
            code, merge_commit_sha, err = await self._run_git(
                "commit-tree", merge_tree_sha,
                "-p", target_sha, "-p", candidate_sha,
                "-m", merge_msg,
            )
            if code != 0:
                raise WorktreeError(
                    f"Failed to create merge commit for {branch_name}: {err}"
                )
            merge_commit_sha = merge_commit_sha.strip()
            code, _, err = await self._run_git(
                "update-ref", f"refs/heads/{target_branch}", merge_commit_sha, target_sha
            )
            if code != 0:
                raise WorktreeError(
                    f"Failed to update ref {target_branch} after merge: {err}"
                )

        # Sync the main worktree's working tree to the new HEAD without switching branches
        await self._run_git("reset", "--hard", "HEAD")

        # Emit accepted event; fix #8: use EventType enum value
        await self._emit_event(
            EventType.WORKTREE_ACCEPTED.value,
            task_id,
            {"tool_name": "worktree_accepted", "tool_input": task_id},
        )

        # Tear down worktree (cleanup emits teardown event + deletes branch)
        await self.cleanup(task_id, force=True)

    async def spawn_pool(
        self, task_id: str, n: int, base_branch: str = "HEAD"
    ) -> WorktreePool:
        """Spawn N candidate worktrees for one logical task.

        Each candidate is named ``{task_id}-{i}`` with branch
        ``grind/{task_id}-{i}``.

        Args:
            task_id: Logical task identifier shared by all candidates.
            n: Number of candidate worktrees to create.
            base_branch: Git ref used as the base for every candidate branch.

        Returns:
            A :class:`WorktreePool` containing the candidate task_ids.

        Raises:
            WorktreeError: If any candidate worktree fails to create.
        """
        # fix #2: rollback on partial failure
        created: list[str] = []
        try:
            for i in range(n):
                candidate_id = f"{task_id}-{i}"
                branch = f"grind/{task_id}-{i}"
                await self.create(candidate_id, branch, base_branch)
                created.append(candidate_id)
        except Exception:
            for cid in created:
                try:
                    await self.cleanup(cid, force=True)
                except WorktreeError:
                    pass
            raise
        return WorktreePool(task_id=task_id, candidates=created)

    async def accept_from_pool(
        self,
        pool: WorktreePool,
        winner_idx: int,
        target_branch: str = "main",
    ) -> None:
        """Accept one worktree from a pool and tear down the rest.

        Args:
            pool: The :class:`WorktreePool` returned by :meth:`spawn_pool`.
            winner_idx: Index into ``pool.candidates`` identifying the winner.
            target_branch: Branch that receives the winning merge.

        Raises:
            IndexError: If ``winner_idx`` is out of range.
            WorktreeError: If acceptance or cleanup fails.
        """
        # fix #4: guard against concurrent accept
        if pool.accepted is not None:
            raise WorktreeError(
                f"Pool '{pool.task_id}' already has an accepted worktree: {pool.accepted}"
            )

        winner_id = pool.candidates[winner_idx]  # fix #9: use candidates

        # Accept the winner (merge + teardown)
        await self.accept(winner_id, target_branch)

        # Tear down all remaining candidates
        for wt_id in pool.candidates:  # fix #9: use candidates
            if wt_id == winner_id:
                continue
            try:
                await self.cleanup(wt_id, force=True)
            except WorktreeError:
                pass  # best-effort; don't abort if one cleanup fails

        pool.accepted = winner_id
