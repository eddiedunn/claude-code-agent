"""Agent team primitives — single self-evolution loop (Phase 4).

Default team shape: one worker, an acceptance gate, retry-on-failure with
narrow expansion. No reviewer agents, no multi-candidate search — both hurt
benchmark scores per Tsinghua/Stanford ablations (PHASES.md).
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from grind.contract import ContractResult, ContractStatus, ExecutionContract, validate
from grind.observer.models import EventType
from grind.worktree import WorktreeManager


@dataclass
class AgentTask:
    """Declaration of a task for the self-evolution loop."""

    task_id: str
    prompt: str
    contract: ExecutionContract
    max_retries: int = 3
    worktree_base_branch: str = "HEAD"


@dataclass
class AgentResult:
    """Outcome of a self-evolution loop run."""

    task_id: str
    status: str  # "accepted" or "failed"
    attempts: int
    final_worktree_path: Path | None = None
    contract_result: ContractResult | None = None


class SelfEvolutionLoop:
    """Single worker, acceptance gate, retry-on-failure.

    The loop never calls an LLM directly. Execution is delegated to the
    caller via an optional ``executor`` callback so tests can simulate agent
    work by writing state/ files without a real model.
    """

    def __init__(
        self,
        repo_root: str,
        observer_url: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.observer_url = observer_url

    def _emit(
        self,
        event_type: str,
        session_id: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        if not self.observer_url:
            return
        payload: dict[str, object] = {
            "event_type": event_type,
            "session_id": session_id,
            "agent_name": session_id,
            "timestamp": time.time(),
            **(extra or {}),
        }
        try:
            req = urllib.request.Request(
                f"{self.observer_url}/events",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

    async def run(
        self,
        task: AgentTask,
        executor: Callable[[AgentTask, Path, int], Awaitable[None]] | None = None,
    ) -> AgentResult:
        """Execute the self-evolution loop for one task.

        For each attempt:
        1. Emit AGENT_SPAWN (attempt 1) or AGENT_RETRY (attempt > 1).
        2. Create a fresh worktree.
        3. Call executor(task, worktree_path, attempt) if provided.
        4. Validate the contract.
        5. FULFILLED → clean up, emit AGENT_COMPLETE, return accepted result.
        6. VIOLATED / TIMEOUT → clean up, continue retrying.
        7. Exhausted → emit AGENT_COMPLETE, return failed result.
        """
        mgr = WorktreeManager(repo_root=self.repo_root, observer_url=self.observer_url)
        max_retries = task.max_retries
        last_result: ContractResult | None = None

        for attempt in range(1, max_retries + 1):
            if attempt == 1:
                self._emit(
                    EventType.AGENT_SPAWN.value,
                    task.task_id,
                    {"attempt": attempt},
                )
            else:
                self._emit(
                    EventType.AGENT_RETRY.value,
                    task.task_id,
                    {"attempt": attempt},
                )

            worktree_id = f"{task.task_id}-attempt-{attempt}"
            branch = f"grind/{task.task_id}-{attempt}"
            worktree_path = await mgr.create(worktree_id, branch, task.worktree_base_branch)

            try:
                if executor is not None:
                    await executor(task, worktree_path, attempt)

                last_result = validate(
                    task.contract,
                    worktree_path,
                    observer_url=self.observer_url,
                    session_id=task.task_id,
                )
            finally:
                await mgr.cleanup(worktree_id, force=True)

            if last_result.status == ContractStatus.FULFILLED:
                self._emit(
                    EventType.AGENT_COMPLETE.value,
                    task.task_id,
                    {"status": "accepted", "attempts": attempt},
                )
                return AgentResult(
                    task_id=task.task_id,
                    status="accepted",
                    attempts=attempt,
                    final_worktree_path=None,
                    contract_result=last_result,
                )

        self._emit(
            EventType.AGENT_COMPLETE.value,
            task.task_id,
            {"status": "failed", "attempts": max_retries},
        )
        return AgentResult(
            task_id=task.task_id,
            status="failed",
            attempts=max_retries,
            final_worktree_path=None,
            contract_result=last_result,
        )
