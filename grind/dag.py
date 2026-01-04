"""DAG-based task execution with dependency ordering.

This module provides the DAGExecutor class for running tasks that have
dependencies on each other. Tasks are executed in topological order,
ensuring all dependencies complete before a task starts.

See docs/dag-execution-design.md for architecture details.
"""

import asyncio
from datetime import datetime
from time import time
from typing import Callable

from grind.engine import grind
from grind.logging import (
    log_session_summary,
    log_session_task_end,
    log_session_task_start,
    setup_session,
    write_session_summary,
)
from grind.models import DAGResult, GrindResult, GrindStatus, TaskGraph, TaskNode
from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.worktree import WorktreeManager


class DAGExecutor:
    """Executes task graphs respecting dependencies.

    This executor runs tasks in topological order, ensuring all dependencies
    complete before a task starts. Tasks blocked by failed dependencies are
    marked as blocked and skipped.

    Usage:
        graph = build_task_graph("tasks.yaml")
        executor = DAGExecutor(graph)
        result = await executor.execute(verbose=True)
    """

    def __init__(self, graph: TaskGraph, event_bus: EventBus | None = None):
        """Initialize executor with a task graph.

        Args:
            graph: The TaskGraph to execute
            event_bus: Optional EventBus for emitting task events
        """
        self.graph = graph
        self.event_bus = event_bus
        self.completed: set[str] = set()
        self.stuck: set[str] = set()
        self.max_iterations: set[str] = set()
        self.failed: set[str] = set()
        self.blocked: set[str] = set()
        self.results: dict[str, GrindResult] = {}

    def _has_failed_dependencies(self, node: TaskNode) -> bool:
        """Check if any dependencies have failed or are blocked."""
        return any(
            d in self.failed or d in self.stuck or
            d in self.max_iterations or d in self.blocked
            for d in node.depends_on
        )

    def _dependencies_completed(self, node: TaskNode) -> bool:
        """Check if all dependencies have completed successfully."""
        return all(d in self.completed for d in node.depends_on)

    def _find_ready_and_blocked_tasks(
        self, pending: set[str]
    ) -> tuple[list[TaskNode], list[str]]:
        """Identify tasks ready to run and newly blocked tasks.

        Args:
            pending: Set of pending task IDs

        Returns:
            Tuple of (ready_nodes, newly_blocked_task_ids)
        """
        ready = []
        newly_blocked = []

        for task_id in pending:
            node = self.graph.nodes[task_id]

            if self._has_failed_dependencies(node):
                newly_blocked.append(task_id)
            elif self._dependencies_completed(node):
                ready.append(node)

        return ready, newly_blocked

    def _mark_tasks_blocked(
        self,
        task_ids: list[str],
        pending: set[str],
        on_task_complete: Callable[[TaskNode, GrindResult], None] | None,
    ) -> None:
        """Mark tasks as blocked due to failed dependencies.

        Args:
            task_ids: List of task IDs to mark as blocked
            pending: Set to remove blocked tasks from
            on_task_complete: Optional callback to invoke
        """
        for task_id in task_ids:
            pending.discard(task_id)
            self.blocked.add(task_id)
            node = self.graph.nodes[task_id]
            node.status = "blocked"
            self.results[task_id] = GrindResult(
                status=GrindStatus.ERROR,
                iterations=0,
                message="Blocked by failed dependencies",
                model=node.task_def.model,
            )
            if on_task_complete:
                on_task_complete(node, self.results[task_id])

    async def _setup_worktree(
        self,
        node: TaskNode,
        worktree_manager: WorktreeManager,
    ) -> str | None:
        """Setup worktree for task isolation.

        Args:
            node: Task node to setup worktree for
            worktree_manager: Worktree manager instance

        Returns:
            Path to worktree or None if setup failed

        Raises:
            Exception: If worktree setup fails
        """
        worktree_path = await worktree_manager.create(
            node.id,
            node.worktree.branch,
            node.worktree.base_branch,
        )
        if node.worktree.merge_from:
            await worktree_manager.merge_branches(
                worktree_path, node.worktree.merge_from
            )
        # Override task cwd to worktree
        node.task_def.cwd = str(worktree_path)
        return worktree_path

    async def _cleanup_worktree(
        self,
        node: TaskNode,
        worktree_manager: WorktreeManager,
        on_success: bool,
    ) -> None:
        """Cleanup worktree after task completion.

        Args:
            node: Task node
            worktree_manager: Worktree manager instance
            on_success: Whether task succeeded
        """
        should_cleanup = (
            (on_success and node.worktree.cleanup_on_success) or
            (not on_success and node.worktree.cleanup_on_failure)
        )
        if should_cleanup:
            try:
                await worktree_manager.cleanup(node.id)
            except Exception:
                pass  # Non-fatal

    def _update_task_status(self, node: TaskNode, result: GrindResult) -> None:
        """Update task status based on execution result.

        Args:
            node: Task node to update
            result: Execution result
        """
        if result.status == GrindStatus.COMPLETE:
            self.completed.add(node.id)
            node.status = "completed"
        elif result.status == GrindStatus.STUCK:
            self.stuck.add(node.id)
            node.status = "stuck"
        elif result.status == GrindStatus.MAX_ITERATIONS:
            self.max_iterations.add(node.id)
            node.status = "max_iterations"
        else:
            self.failed.add(node.id)
            node.status = "failed"

    async def _run_single_task(
        self,
        node: TaskNode,
        semaphore: asyncio.Semaphore,
        verbose: bool,
        use_worktrees: bool,
        worktree_manager: WorktreeManager | None,
        on_task_start: Callable[[TaskNode], None] | None,
        on_task_complete: Callable[[TaskNode, GrindResult], None] | None,
    ) -> None:
        """Run a single task with optional worktree isolation.

        Args:
            node: Task node to execute
            semaphore: Semaphore for concurrency control
            verbose: Pass to grind() for detailed output
            use_worktrees: Whether to use worktrees
            worktree_manager: Worktree manager instance
            on_task_start: Called when a task begins
            on_task_complete: Called when a task finishes
        """
        async with semaphore:
            worktree_path = None

            # Setup worktree if configured
            if use_worktrees and node.worktree and worktree_manager:
                try:
                    worktree_path = await self._setup_worktree(
                        node, worktree_manager
                    )
                except Exception as e:
                    self.failed.add(node.id)
                    node.status = "failed"
                    self.results[node.id] = GrindResult(
                        status=GrindStatus.ERROR,
                        iterations=0,
                        message=f"Worktree setup failed: {e}",
                        model=node.task_def.model,
                    )
                    if on_task_complete:
                        on_task_complete(node, self.results[node.id])
                    return

            node.status = "running"

            # Emit TASK_STARTED event
            if self.event_bus:
                await self.event_bus.publish(AgentEvent(
                    event_type=EventType.TASK_STARTED,
                    agent_id=node.id,
                    data={"task": node.task_def.task},
                    timestamp=time(),
                ))

            # Log task start (use execution order index as task_index)
            # Since tasks can run in parallel, we'll use a simple counter
            log_session_task_start(
                task_id=node.id,
                task_name=node.task_def.task,
                task_index=1  # Will be incremented by setup_logger
            )

            if on_task_start:
                on_task_start(node)

            task_start_time = datetime.now()
            result = await grind(node.task_def, verbose=verbose)
            task_duration = (datetime.now() - task_start_time).total_seconds()
            self.results[node.id] = result

            self._update_task_status(node, result)

            # Log task end
            log_session_task_end(
                task_id=node.id,
                status=result.status.value,
                duration=task_duration
            )

            # Cleanup worktree if needed
            if worktree_path and node.worktree and worktree_manager:
                await self._cleanup_worktree(
                    node,
                    worktree_manager,
                    result.status == GrindStatus.COMPLETE,
                )

            # Emit TASK_COMPLETED or TASK_FAILED event
            if self.event_bus:
                event_type = (
                    EventType.TASK_COMPLETED
                    if result.status == GrindStatus.COMPLETE
                    else EventType.TASK_FAILED
                )
                await self.event_bus.publish(AgentEvent(
                    event_type=event_type,
                    agent_id=node.id,
                    data={
                        "status": result.status.value,
                        "iterations": result.iterations,
                        "message": result.message,
                    },
                    timestamp=time(),
                ))

            if on_task_complete:
                on_task_complete(node, result)

    async def execute(
        self,
        verbose: bool = False,
        max_parallel: int = 1,
        use_worktrees: bool = False,
        on_task_start: Callable[[TaskNode], None] | None = None,
        on_task_complete: Callable[[TaskNode, GrindResult], None] | None = None,
        task_file: str | None = None,
    ) -> DAGResult:
        """Execute all tasks in dependency order with optional parallelism.

        Args:
            verbose: Pass to grind() for detailed output
            max_parallel: Maximum concurrent tasks (default 1 = sequential)
            use_worktrees: Use Git worktrees for task isolation
            on_task_start: Called when a task begins
            on_task_complete: Called when a task finishes
            task_file: Path to task file for session logging

        Returns:
            DAGResult with execution summary and per-task results
        """
        # Setup session-based logging at the start
        setup_session(task_file=task_file)

        start_time = datetime.now()
        execution_order: list[str] = []
        worktree_manager = WorktreeManager() if use_worktrees else None
        semaphore = asyncio.Semaphore(max_parallel)

        # Main execution loop
        pending = set(self.graph.nodes.keys())

        while pending:
            ready, newly_blocked = self._find_ready_and_blocked_tasks(pending)

            self._mark_tasks_blocked(newly_blocked, pending, on_task_complete)

            if not ready and not newly_blocked:
                break  # No more tasks can run or be blocked

            # Record execution order and remove from pending
            for node in ready:
                execution_order.append(node.id)
                pending.discard(node.id)

            # Run ready tasks in parallel (semaphore limits concurrency)
            tasks = [
                self._run_single_task(
                    node,
                    semaphore,
                    verbose,
                    use_worktrees,
                    worktree_manager,
                    on_task_start,
                    on_task_complete,
                )
                for node in ready
            ]
            await asyncio.gather(*tasks)

        duration = (datetime.now() - start_time).total_seconds()

        # Prepare task results for session summary
        task_results = []
        for task_id in execution_order:
            node = self.graph.nodes[task_id]
            result = self.results.get(task_id)
            if result:
                task_results.append({
                    "id": task_id,
                    "task": node.task_def.task,
                    "status": result.status.value,
                    "duration": result.duration_seconds,
                    "iterations": result.iterations,
                    "message": result.message or ""
                })

        # Add blocked tasks to results
        for task_id in self.blocked:
            node = self.graph.nodes[task_id]
            result = self.results.get(task_id)
            if result:
                task_results.append({
                    "id": task_id,
                    "task": node.task_def.task,
                    "status": result.status.value,
                    "duration": 0,
                    "iterations": result.iterations,
                    "message": result.message or ""
                })

        # Write session summary and log it
        write_session_summary(
            task_file=task_file,
            tasks=task_results,
            total_duration=duration,
            start_time=start_time
        )
        log_session_summary(
            total=len(self.graph.nodes),
            completed=len(self.completed),
            stuck=len(self.stuck),
            failed=len(self.failed) + len(self.max_iterations) + len(self.blocked),
            duration=duration
        )

        return DAGResult(
            total=len(self.graph.nodes),
            completed=len(self.completed),
            stuck=len(self.stuck),
            max_iterations=len(self.max_iterations),
            failed=len(self.failed),
            blocked=len(self.blocked),
            execution_order=execution_order,
            results=self.results,
            duration_seconds=duration,
        )
