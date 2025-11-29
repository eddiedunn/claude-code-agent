"""DAG-based task execution with dependency ordering.

This module provides the DAGExecutor class for running tasks that have
dependencies on each other. Tasks are executed in topological order,
ensuring all dependencies complete before a task starts.

See docs/dag-execution-design.md for architecture details.
"""

import asyncio
from datetime import datetime
from typing import Callable

from grind.engine import grind
from grind.models import DAGResult, GrindResult, GrindStatus, TaskGraph, TaskNode
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

    def __init__(self, graph: TaskGraph):
        """Initialize executor with a task graph.

        Args:
            graph: The TaskGraph to execute
        """
        self.graph = graph
        self.completed: set[str] = set()
        self.failed: set[str] = set()
        self.blocked: set[str] = set()
        self.results: dict[str, GrindResult] = {}

    async def execute(
        self,
        verbose: bool = False,
        max_parallel: int = 1,
        use_worktrees: bool = False,
        on_task_start: Callable[[TaskNode], None] | None = None,
        on_task_complete: Callable[[TaskNode, GrindResult], None] | None = None,
    ) -> DAGResult:
        """Execute all tasks in dependency order with optional parallelism.

        Args:
            verbose: Pass to grind() for detailed output
            max_parallel: Maximum concurrent tasks (default 1 = sequential)
            use_worktrees: Use Git worktrees for task isolation
            on_task_start: Called when a task begins
            on_task_complete: Called when a task finishes

        Returns:
            DAGResult with execution summary and per-task results
        """
        start_time = datetime.now()
        execution_order: list[str] = []

        # Initialize worktree manager if needed
        worktree_manager = WorktreeManager() if use_worktrees else None

        # Semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_parallel)

        async def run_single_task(node: TaskNode) -> None:
            """Run a single task with optional worktree isolation."""
            async with semaphore:
                worktree_path = None

                # Setup worktree if configured
                if use_worktrees and node.worktree and worktree_manager:
                    try:
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
                if on_task_start:
                    on_task_start(node)

                result = await grind(node.task_def, verbose=verbose)
                self.results[node.id] = result

                if result.status == GrindStatus.COMPLETE:
                    self.completed.add(node.id)
                    node.status = "completed"
                    # Cleanup worktree on success
                    if (worktree_path and node.worktree and
                            node.worktree.cleanup_on_success and worktree_manager):
                        try:
                            await worktree_manager.cleanup(node.id)
                        except Exception:
                            pass  # Non-fatal
                else:
                    self.failed.add(node.id)
                    node.status = "failed"
                    # Optionally cleanup on failure
                    if (worktree_path and node.worktree and
                            node.worktree.cleanup_on_failure and worktree_manager):
                        try:
                            await worktree_manager.cleanup(node.id)
                        except Exception:
                            pass

                if on_task_complete:
                    on_task_complete(node, result)

        # Main execution loop
        pending = set(self.graph.nodes.keys())

        while pending:
            # Find ready tasks
            ready = []
            newly_blocked = []

            for task_id in list(pending):
                node = self.graph.nodes[task_id]
                failed_deps = [
                    d for d in node.depends_on
                    if d in self.failed or d in self.blocked
                ]

                if failed_deps:
                    newly_blocked.append(task_id)
                elif all(d in self.completed for d in node.depends_on):
                    ready.append(node)

            # Mark newly blocked tasks
            for task_id in newly_blocked:
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

            if not ready and not newly_blocked:
                break  # No more tasks can run or be blocked

            # Record execution order
            for node in ready:
                execution_order.append(node.id)
                pending.discard(node.id)

            # Run ready tasks in parallel (semaphore limits concurrency)
            await asyncio.gather(*[run_single_task(node) for node in ready])

        duration = (datetime.now() - start_time).total_seconds()

        return DAGResult(
            total=len(self.graph.nodes),
            completed=len(self.completed),
            failed=len(self.failed),
            blocked=len(self.blocked),
            execution_order=execution_order,
            results=self.results,
            duration_seconds=duration,
        )
