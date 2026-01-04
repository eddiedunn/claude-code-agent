"""Smart merge assistant for grind DAG results.

This module provides the GrindMerger class for intelligently merging
multiple task branches with interactive conflict resolution. It handles
clean merges automatically and prompts humans only when conflicts occur.

Safety features:
- Creates backup branches before merging
- Works in staging branches (never touches target directly)
- Detects conflicts without auto-resolving
- Provides verification step
- Clear rollback instructions
"""

import asyncio
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from grind.logging import get_logger

logger = get_logger()


class MergeError(Exception):
    """Error during merge operations."""
    pass


@dataclass
class MergeAttempt:
    """Result of attempting to merge a single branch.

    Attributes:
        branch: Name of the branch being merged
        status: Outcome of the merge attempt
        conflict_files: List of files with merge conflicts (if any)
        resolution: How the conflict was resolved (if applicable)
    """
    branch: str
    status: Literal["success", "conflict", "skipped", "failed"]
    conflict_files: list[str] = field(default_factory=list)
    resolution: str | None = None


@dataclass
class MergeSession:
    """State for an entire merge session.

    Tracks all merge attempts and provides summary statistics.

    Attributes:
        target_branch: Original target branch
        staging_branch: Temporary branch where merges are performed
        backup_branch: Safety backup of original state
        attempts: List of all merge attempts
        verification_passed: Whether post-merge verification succeeded
        verification_command: Command used for verification
        aborted: Whether the session was aborted
    """
    target_branch: str
    staging_branch: str
    backup_branch: str
    attempts: list[MergeAttempt] = field(default_factory=list)
    verification_passed: bool = False
    verification_command: str | None = None
    aborted: bool = False

    @property
    def success_count(self) -> int:
        """Number of successfully merged branches."""
        return sum(1 for a in self.attempts if a.status == "success")

    @property
    def conflict_count(self) -> int:
        """Number of branches that had conflicts."""
        return sum(1 for a in self.attempts if a.status == "conflict")

    @property
    def skipped_count(self) -> int:
        """Number of branches that were skipped."""
        return sum(1 for a in self.attempts if a.status == "skipped")

    @property
    def skipped_branches(self) -> list[str]:
        """List of branch names that were skipped."""
        return [a.branch for a in self.attempts if a.status == "skipped"]


class GrindMerger:
    """Interactive merge assistant for grind task branches.

    Provides intelligent merging with:
    - Automatic handling of clean merges
    - Interactive prompts for conflicts only
    - Safety features (backup, staging, verification)
    - Clear rollback instructions

    Usage:
        merger = GrindMerger()
        branches = ["fix/lint", "fix/tests", "fix/types"]
        session = await merger.merge_branches(branches, target="main")
        print_merge_summary(session)
    """

    def __init__(self, repo_root: str | None = None):
        """Initialize merger.

        Args:
            repo_root: Git repository root. Auto-detected if None.
        """
        if repo_root:
            self.repo_root = Path(repo_root)
        else:
            self.repo_root = self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find git repository root from current directory."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MergeError("Not in a git repository")
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
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    async def _get_current_branch(self) -> str:
        """Get name of current branch."""
        code, out, _ = await self._run_git("branch", "--show-current")
        if code != 0:
            raise MergeError("Failed to get current branch")
        return out.strip()

    async def _branch_exists(self, branch: str) -> bool:
        """Check if a branch exists."""
        code, _, _ = await self._run_git("rev-parse", "--verify", f"refs/heads/{branch}")
        return code == 0

    async def _get_conflict_files(self) -> list[str]:
        """Get list of files with merge conflicts."""
        code, out, _ = await self._run_git("diff", "--name-only", "--diff-filter=U")
        if code != 0:
            return []
        return [f.strip() for f in out.strip().split("\n") if f.strip()]

    async def _show_conflict_diff(self, files: list[str]) -> None:
        """Display conflict diff for files."""
        for file in files:
            print(f"\n{'='*60}")
            print(f"Conflicts in: {file}")
            print('='*60)
            code, out, _ = await self._run_git("diff", file)
            if code == 0:
                print(out)

    def _prompt_conflict_resolution(
        self,
        branch: str,
        conflict_files: list[str]
    ) -> str:
        """Prompt user for conflict resolution strategy.

        Args:
            branch: Branch being merged
            conflict_files: List of files with conflicts

        Returns:
            Resolution choice: "ours", "theirs", "skip", "abort"
        """
        print(f"\n⚠️  Conflict merging {branch}")
        print("\nFiles in conflict:")
        for f in conflict_files:
            print(f"  - {f}")

        print("\nOptions:")
        print("  [1] Show diff (investigate)")
        print("  [2] Keep ours (discard their changes)")
        print("  [3] Keep theirs (accept their changes)")
        print("  [4] Skip this branch")
        print("  [5] Abort entire merge")

        while True:
            choice = input("\nChoice [1-5]: ").strip()

            if choice == "1":
                asyncio.run(self._show_conflict_diff(conflict_files))
                continue
            elif choice == "2":
                return "ours"
            elif choice == "3":
                return "theirs"
            elif choice == "4":
                return "skip"
            elif choice == "5":
                return "abort"
            else:
                print("Invalid choice. Please enter 1-5.")

    async def _merge_single_branch(
        self,
        branch: str,
        interactive: bool
    ) -> MergeAttempt:
        """Attempt to merge a single branch.

        Args:
            branch: Branch name to merge
            interactive: Whether to prompt on conflicts

        Returns:
            MergeAttempt with result
        """
        attempt = MergeAttempt(branch=branch, status="success")

        logger.info(f"Attempting to merge {branch}")

        code, stdout, stderr = await self._run_git(
            "merge", branch, "--no-ff", "--no-edit"
        )

        if code == 0:
            logger.info(f"✓ {branch} (clean)")
            attempt.status = "success"
            return attempt

        conflict_files = await self._get_conflict_files()
        attempt.conflict_files = conflict_files
        attempt.status = "conflict"

        if not interactive:
            logger.warning(f"⚠️  {branch} (conflict - aborting)")
            await self._run_git("merge", "--abort")
            return attempt

        resolution = self._prompt_conflict_resolution(branch, conflict_files)

        if resolution == "ours":
            await self._run_git("checkout", "--ours", ".")
            await self._run_git("add", ".")
            await self._run_git("commit", "--no-edit")
            attempt.status = "success"
            attempt.resolution = "ours"
            logger.info(f"✓ {branch} (resolved: ours)")

        elif resolution == "theirs":
            await self._run_git("checkout", "--theirs", ".")
            await self._run_git("add", ".")
            await self._run_git("commit", "--no-edit")
            attempt.status = "success"
            attempt.resolution = "theirs"
            logger.info(f"✓ {branch} (resolved: theirs)")

        elif resolution == "skip":
            await self._run_git("merge", "--abort")
            attempt.status = "skipped"
            logger.info(f"⊘ {branch} (skipped)")

        elif resolution == "abort":
            await self._run_git("merge", "--abort")
            attempt.status = "failed"
            logger.info(f"✗ {branch} (user aborted)")

        return attempt

    async def _verify_merge(
        self,
        command: str,
        session: MergeSession,
    ) -> bool:
        """Run verification command on merged result.

        Args:
            command: Shell command to run
            session: Current merge session

        Returns:
            True if verification passed
        """
        print(f"\n🧪 Running verification: {command}")

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            print("✓ Verification passed")
            return True
        else:
            print("✗ Verification failed")
            print("\nStdout:")
            print(stdout.decode())
            print("\nStderr:")
            print(stderr.decode())
            return False

    async def _rollback(self, session: MergeSession) -> None:
        """Rollback to pre-merge state.

        Args:
            session: Merge session to rollback
        """
        logger.info("Rolling back merge session")
        await self._run_git("checkout", session.target_branch)
        await self._run_git("branch", "-D", session.staging_branch)

    def find_branches(self, pattern: str) -> list[str]:
        """Find branches matching pattern.

        Args:
            pattern: Comma-separated glob patterns (e.g., "fix/*,grind/*")

        Returns:
            List of matching branch names
        """
        result = subprocess.run(
            ["git", "branch", "--list", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )

        if result.returncode != 0:
            return []

        all_branches = [b.strip() for b in result.stdout.split("\n") if b.strip()]

        patterns = [p.strip() for p in pattern.split(",")]
        matched = []

        for branch in all_branches:
            for pat in patterns:
                if self._matches_pattern(branch, pat):
                    matched.append(branch)
                    break

        return matched

    def _matches_pattern(self, branch: str, pattern: str) -> bool:
        """Check if branch matches glob pattern.

        Args:
            branch: Branch name
            pattern: Glob pattern (e.g., "fix/*")

        Returns:
            True if matches
        """
        if "*" not in pattern:
            return branch == pattern

        import fnmatch
        return fnmatch.fnmatch(branch, pattern)

    async def merge_branches(
        self,
        branches: list[str],
        target: str | None = None,
        verify_command: str | None = None,
        interactive: bool = True,
    ) -> MergeSession:
        """Merge multiple branches with conflict resolution assistance.

        Args:
            branches: List of branch names to merge
            target: Target branch (default: current branch)
            verify_command: Optional command to run after merging
            interactive: Whether to prompt for conflict resolution

        Returns:
            MergeSession with results
        """
        if not branches:
            raise MergeError("No branches to merge")

        if target is None:
            target = await self._get_current_branch()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        session = MergeSession(
            target_branch=target,
            staging_branch=f"grind-merge-{timestamp}",
            backup_branch=f"grind-backup-{timestamp}",
            verification_command=verify_command,
        )

        print(f"\n🔍 Found {len(branches)} branches to merge")
        print(f"📝 Creating staging branch: {session.staging_branch}")
        print(f"💾 Backup created: {session.backup_branch}")

        code, _, _ = await self._run_git("branch", session.backup_branch)
        if code != 0:
            raise MergeError("Failed to create backup branch")

        code, _, _ = await self._run_git("checkout", "-b", session.staging_branch, target)
        if code != 0:
            raise MergeError("Failed to create staging branch")

        print("\nMerging branches...")

        for branch in branches:
            if not await self._branch_exists(branch):
                logger.warning(f"Branch {branch} does not exist, skipping")
                continue

            attempt = await self._merge_single_branch(branch, interactive)
            session.attempts.append(attempt)

            if attempt.status == "failed":
                session.aborted = True
                await self._rollback(session)
                return session

        if verify_command:
            session.verification_passed = await self._verify_merge(
                verify_command,
                session,
            )

        return session
