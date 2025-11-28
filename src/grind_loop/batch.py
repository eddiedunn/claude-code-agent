"""
Batch processing for multiple grind tasks.
"""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml

from grind_loop.core import GrindResult, GrindStatus, grind


@dataclass
class TaskDefinition:
    """A single task to grind on."""

    task: str
    verify: str
    max_iterations: int = 10
    cwd: str | None = None


@dataclass
class BatchResult:
    """Result of a batch run."""

    total: int
    completed: int
    stuck: int
    failed: int
    results: list[tuple[str, GrindResult]]
    duration_seconds: float


def load_tasks(path: str | Path) -> list[TaskDefinition]:
    """
    Load tasks from a YAML or JSON file.

    YAML format:
        tasks:
          - task: "Fix auth tests"
            verify: "pytest tests/auth/ -v"
          - task: "Fix SonarQube issues in utils"
            verify: "./sonar-check.sh"
            max_iterations: 5

    JSON format:
        {"tasks": [{"task": "...", "verify": "..."}, ...]}
    """
    path = Path(path)
    content = path.read_text()

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    tasks = []
    for item in data.get("tasks", []):
        tasks.append(
            TaskDefinition(
                task=item["task"],
                verify=item["verify"],
                max_iterations=item.get("max_iterations", 10),
                cwd=item.get("cwd"),
            )
        )
    return tasks


async def run_batch(
    tasks: list[TaskDefinition],
    verbose: bool = False,
    stop_on_stuck: bool = False,
) -> BatchResult:
    """
    Run multiple grind tasks sequentially.

    Args:
        tasks: List of tasks to process
        verbose: Show detailed output
        stop_on_stuck: Stop batch if any task gets stuck

    Returns:
        BatchResult with aggregate statistics
    """
    start_time = datetime.now()
    results: list[tuple[str, GrindResult]] = []

    completed = 0
    stuck = 0
    failed = 0

    for i, task_def in enumerate(tasks, 1):
        print(f"\n{'#'*60}")
        print(f"# TASK {i}/{len(tasks)}: {task_def.task[:50]}...")
        print(f"{'#'*60}")

        result = await grind(
            task=task_def.task,
            verify_cmd=task_def.verify,
            max_iterations=task_def.max_iterations,
            cwd=task_def.cwd,
            verbose=verbose,
            on_iteration=lambda n, s: print(f"  [Iteration {n}]") if not verbose else None,
        )

        results.append((task_def.task, result))

        if result.status == GrindStatus.COMPLETE:
            completed += 1
            print(f"  -> COMPLETE in {result.iterations} iterations")
        elif result.status == GrindStatus.STUCK:
            stuck += 1
            print(f"  -> STUCK: {result.message}")
            if stop_on_stuck:
                print("\nStopping batch (--stop-on-stuck)")
                break
        else:
            failed += 1
            print(f"  -> FAILED: {result.status.value}")

    duration = (datetime.now() - start_time).total_seconds()

    return BatchResult(
        total=len(tasks),
        completed=completed,
        stuck=stuck,
        failed=failed,
        results=results,
        duration_seconds=duration,
    )


def print_batch_summary(result: BatchResult) -> None:
    """Print a summary of batch results."""
    print("\n" + "=" * 60)
    print("BATCH SUMMARY")
    print("=" * 60)
    print(f"Total tasks:  {result.total}")
    print(f"Completed:    {result.completed}")
    print(f"Stuck:        {result.stuck}")
    print(f"Failed:       {result.failed}")
    print(f"Duration:     {result.duration_seconds:.1f}s")
    print()

    if result.stuck > 0 or result.failed > 0:
        print("Tasks needing attention:")
        for task, res in result.results:
            if res.status != GrindStatus.COMPLETE:
                print(f"  - [{res.status.value}] {task[:60]}")
                if res.message:
                    print(f"    Reason: {res.message}")
