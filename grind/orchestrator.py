"""Orchestrator — planner + generator + using-evaluator (Phase 6).

Single interface implementing Anthropic's planner + generator + evaluator
pattern. The evaluator actually *uses* the output — not a log reader or
diff reader. This is the part most orchestrators skip.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from grind.contract import ExecutionContract
from grind.observer.models import EventType
from grind.team import AgentResult, AgentTask, SelfEvolutionLoop


@dataclass
class OrchestratorStep:
    """One contracted unit of work within an orchestrated plan."""

    step_id: str
    prompt: str
    contract: ExecutionContract
    max_retries: int = 3


@dataclass
class OrchestratorResult:
    """Outcome of a full orchestrated plan run."""

    status: str  # "accepted" | "failed"
    plan_attempts: int
    step_results: list[AgentResult] = field(default_factory=list)


class Orchestrator:
    """Planner + generator + using-evaluator in a single interface.

    - Generator: runs each step through a SelfEvolutionLoop, sequential order.
    - Evaluator: user-supplied callback; receives all AgentResults, returns bool.
    - If evaluator is None, accept iff all steps returned status="accepted".
    - If evaluator returns False, retry the full plan up to max_plan_retries times.

    Emits AGENT_SPAWN on plan start, AGENT_RETRY on each retry, AGENT_COMPLETE
    when done (whether accepted or exhausted).
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
            pass  # observer is optional — never block orchestration

    async def run(
        self,
        goal: str,
        steps: list[OrchestratorStep],
        executor: Callable[[AgentTask, Path, int], Awaitable[None]] | None = None,
        evaluator: Callable[[list[AgentResult]], Awaitable[bool]] | None = None,
        max_plan_retries: int = 2,
    ) -> OrchestratorResult:
        """Execute the plan: generator loop → evaluator → retry on rejection.

        Args:
            goal: Human-readable description of the objective (used as session_id).
            steps: Ordered list of contracted steps to execute sequentially.
            executor: Optional callback that performs work in the worktree.
            evaluator: Optional callback that inspects results and returns bool.
                       If None, accept when all steps returned status="accepted".
            max_plan_retries: Maximum plan attempts before giving up.

        Returns:
            OrchestratorResult with status, plan_attempts, and step_results.
        """
        session_id = goal
        step_results: list[AgentResult] = []

        for attempt in range(1, max_plan_retries + 1):
            if attempt == 1:
                self._emit(
                    EventType.AGENT_SPAWN.value,
                    session_id,
                    {"attempt": attempt, "goal": goal},
                )
            else:
                self._emit(
                    EventType.AGENT_RETRY.value,
                    session_id,
                    {"attempt": attempt, "goal": goal},
                )

            step_results = []
            for step in steps:
                task = AgentTask(
                    task_id=step.step_id,
                    prompt=step.prompt,
                    contract=step.contract,
                    max_retries=step.max_retries,
                )
                loop = SelfEvolutionLoop(
                    repo_root=self.repo_root,
                    observer_url=self.observer_url,
                )
                result = await loop.run(task, executor)
                step_results.append(result)

            if evaluator is not None:
                accepted = await evaluator(step_results)
            else:
                accepted = all(r.status == "accepted" for r in step_results)

            if accepted:
                self._emit(
                    EventType.AGENT_COMPLETE.value,
                    session_id,
                    {"status": "accepted", "plan_attempts": attempt},
                )
                return OrchestratorResult(
                    status="accepted",
                    plan_attempts=attempt,
                    step_results=step_results,
                )

        self._emit(
            EventType.AGENT_COMPLETE.value,
            session_id,
            {"status": "failed", "plan_attempts": max_plan_retries},
        )
        return OrchestratorResult(
            status="failed",
            plan_attempts=max_plan_retries,
            step_results=step_results,
        )
