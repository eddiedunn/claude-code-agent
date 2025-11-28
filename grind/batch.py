from datetime import datetime

from grind.engine import grind
from grind.logging import get_log_file, log_session_end
from grind.models import BatchResult, GrindResult, GrindStatus, TaskDefinition
from grind.utils import Color, print_task_header, print_task_result


async def run_batch(
    tasks: list[TaskDefinition],
    verbose: bool = False,
    stop_on_stuck: bool = False
) -> BatchResult:
    start = datetime.now()
    results: list[tuple[str, GrindResult]] = []
    completed = stuck = failed = 0

    for i, t in enumerate(tasks, 1):
        print_task_header(i, len(tasks), t)

        result = await grind(
            t,
            verbose,
            lambda n, s: print(Color.dim(f"    Iteration {n}...")) if not verbose else None
        )
        results.append((t.task, result))

        print_task_result(result)

        if result.status == GrindStatus.COMPLETE:
            completed += 1
        elif result.status == GrindStatus.STUCK:
            stuck += 1
            if stop_on_stuck:
                print(Color.warning("\n  Stopping batch (--stop-on-stuck)"))
                break
        else:
            failed += 1

    duration = (datetime.now() - start).total_seconds()
    log_session_end(len(tasks), completed, stuck, failed, duration)

    # Print log file location
    log_file = get_log_file()
    if log_file:
        print(Color.dim(f"\n  Log file: {log_file}"))

    return BatchResult(
        len(tasks),
        completed,
        stuck,
        failed,
        results,
        duration
    )
