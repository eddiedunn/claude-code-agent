from datetime import datetime

from grind.engine import grind
from grind.logging import (
    get_log_file,
    log_session_end,
    log_session_summary,
    log_session_task_end,
    log_session_task_start,
    setup_session,
    write_session_summary,
)
from grind.models import BatchResult, GrindResult, GrindStatus, TaskDefinition
from grind.utils import Color, print_task_header, print_task_result


async def run_batch(
    tasks: list[TaskDefinition],
    verbose: bool = False,
    stop_on_stuck: bool = False,
    task_file: str | None = None
) -> BatchResult:
    start = datetime.now()
    results: list[tuple[str, GrindResult]] = []
    completed = stuck = max_iterations = failed = 0

    # Setup session-based logging at the start
    setup_session(task_file=task_file)

    for i, t in enumerate(tasks, 1):
        print_task_header(i, len(tasks), t)

        # Log task start
        task_id = f"task_{i}"
        log_session_task_start(task_id=task_id, task_name=t.task, task_index=i)

        task_start = datetime.now()
        result = await grind(
            t,
            verbose,
            lambda n, s: print(Color.dim(f"    Iteration {n}...")) if not verbose else None
        )
        task_duration = (datetime.now() - task_start).total_seconds()
        results.append((t.task, result))

        # Log task end
        log_session_task_end(task_id=task_id, status=result.status.value, duration=task_duration)

        print_task_result(result)

        if result.status == GrindStatus.COMPLETE:
            completed += 1
        elif result.status == GrindStatus.STUCK:
            stuck += 1
            if stop_on_stuck:
                print(Color.warning("\n  Stopping batch (--stop-on-stuck)"))
                break
        elif result.status == GrindStatus.MAX_ITERATIONS:
            max_iterations += 1
        else:
            failed += 1

    duration = (datetime.now() - start).total_seconds()
    log_session_end(len(tasks), completed, stuck, failed, duration)

    # Prepare task results for summary
    task_results = []
    for i, (task_name, result) in enumerate(results, 1):
        task_results.append({
            "id": f"task_{i}",
            "task": task_name,
            "status": result.status.value,
            "duration": result.duration_seconds,
            "iterations": result.iterations,
            "message": result.message or ""
        })

    # Write session summary and log it
    write_session_summary(
        task_file=task_file,
        tasks=task_results,
        total_duration=duration,
        start_time=start
    )
    log_session_summary(
        total=len(tasks),
        completed=completed,
        stuck=stuck,
        failed=failed,
        duration=duration
    )

    # Print log file location
    log_file = get_log_file()
    if log_file:
        print(Color.dim(f"\n  Log file: {log_file}"))

    return BatchResult(
        len(tasks),
        completed,
        stuck,
        max_iterations,
        failed,
        results,
        duration
    )
