from grind.models import BatchResult, GrindResult, GrindStatus, TaskDefinition


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @staticmethod
    def header(text: str) -> str:
        return f"{Color.BOLD}{Color.CYAN}{text}{Color.RESET}"

    @staticmethod
    def success(text: str) -> str:
        return f"{Color.GREEN}{text}{Color.RESET}"

    @staticmethod
    def error(text: str) -> str:
        return f"{Color.RED}{text}{Color.RESET}"

    @staticmethod
    def warning(text: str) -> str:
        return f"{Color.YELLOW}{text}{Color.RESET}"

    @staticmethod
    def info(text: str) -> str:
        return f"{Color.BLUE}{text}{Color.RESET}"

    @staticmethod
    def dim(text: str) -> str:
        return f"{Color.DIM}{text}{Color.RESET}"

    @staticmethod
    def bold(text: str) -> str:
        return f"{Color.BOLD}{text}{Color.RESET}"

    @staticmethod
    def status_badge(status: GrindStatus) -> str:
        bg = Color.BG_GREEN
        if status in (GrindStatus.STUCK, GrindStatus.MAX_ITERATIONS):
            bg = Color.BG_YELLOW
        elif status == GrindStatus.ERROR:
            bg = Color.BG_RED
        labels = {
            GrindStatus.COMPLETE: "COMPLETE",
            GrindStatus.STUCK: "STUCK",
            GrindStatus.MAX_ITERATIONS: "MAX ITER",
            GrindStatus.ERROR: "ERROR",
        }
        label = labels.get(status, status.value)
        return f"{bg}{Color.WHITE}{Color.BOLD} {label} {Color.RESET}"

    @staticmethod
    def model_badge(model: str) -> str:
        colors = {
            "opus": Color.MAGENTA,
            "sonnet": Color.BLUE,
            "haiku": Color.CYAN,
        }
        color = colors.get(model, Color.WHITE)
        return f"{color}{Color.BOLD}[{model}]{Color.RESET}"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def print_task_header(task_num: int, total: int, task: TaskDefinition) -> None:
    print()
    print(Color.header("=" * 70))
    progress = f"[{task_num}/{total}]"
    model = Color.model_badge(task.model)
    print(f"{Color.bold(progress)} {model} {Color.bold(task.task[:55])}")
    print(Color.dim(f"  Verify: {task.verify}"))
    print(Color.header("-" * 70))


def print_task_result(r: GrindResult) -> None:
    print(Color.header("-" * 70))
    badge = Color.status_badge(r.status)
    duration = format_duration(r.duration_seconds)
    iterations = f"{r.iterations} iteration{'s' if r.iterations != 1 else ''}"

    print(f"  {badge}  {Color.dim(iterations)} | {Color.dim(duration)}")

    if r.message and r.status != GrindStatus.COMPLETE:
        print(f"  {Color.warning('Reason:')} {r.message}")

    if r.hooks_executed:
        hook_summary = []
        for cmd, _, success in r.hooks_executed:
            if success:
                hook_summary.append(Color.success(cmd))
            else:
                hook_summary.append(Color.error(cmd))
        print(f"  {Color.dim('Hooks:')} {' '.join(hook_summary)}")

    print(Color.header("=" * 70))


def print_result(r: GrindResult) -> None:
    labels = {
        GrindStatus.COMPLETE: ("COMPLETE", "Verification passed!", Color.success),
        GrindStatus.STUCK: ("STUCK", "Human intervention needed", Color.warning),
        GrindStatus.MAX_ITERATIONS: ("MAX ITERATIONS", "Limit reached", Color.warning),
        GrindStatus.ERROR: ("ERROR", "Execution failed", Color.error),
    }
    label, desc, color_fn = labels.get(r.status, ("UNKNOWN", "", Color.info))
    print(f"\n{Color.header('=' * 60)}")
    print(color_fn(f"{label} - {desc}"))
    print(Color.header("=" * 60))

    if r.message:
        print(Color.info(f"Message: {r.message}"))

    print(Color.dim(f"Model: {r.model}"))
    print(Color.dim(f"Iterations: {r.iterations}"))
    print(Color.dim(f"Duration: {format_duration(r.duration_seconds)}"))

    if r.tools_used:
        print(Color.dim(f"Tools: {', '.join(r.tools_used)}"))

    if r.hooks_executed:
        print(Color.header(f"\nHooks Executed ({len(r.hooks_executed)}):"))
        for cmd, output, success in r.hooks_executed:
            status_color = Color.success if success else Color.error
            status = "OK" if success else "FAILED"
            print(status_color(f"  [{status}] {cmd}"))


def print_batch_summary(r: BatchResult) -> None:
    print()
    print()
    print(Color.header("=" * 70))
    print(Color.header("  BATCH COMPLETE"))
    print(Color.header("=" * 70))

    # Stats row with colored badges
    def make_badge(bg: str, count: int, label: str) -> str:
        return f"{bg}{Color.WHITE}{Color.BOLD} {count} {label} {Color.RESET}"

    badges = [make_badge(Color.BG_GREEN, r.completed, "COMPLETE")]
    if r.stuck:
        badges.append(make_badge(Color.BG_YELLOW, r.stuck, "STUCK"))
    if r.max_iterations:
        badges.append(make_badge(Color.BG_BLUE, r.max_iterations, "MAX_ITER"))
    if r.failed:
        badges.append(make_badge(Color.BG_RED, r.failed, "FAILED"))

    stats = f"| {r.total} tasks | {format_duration(r.duration_seconds)}"
    print(f"  {' '.join(badges)}  {Color.dim(stats)}")
    print()

    # Task results table
    print(Color.header("  Results:"))
    print(Color.dim("  " + "-" * 66))

    for i, (task, res) in enumerate(r.results, 1):
        # Status indicator
        if res.status == GrindStatus.COMPLETE:
            status = Color.success("[OK]")
        elif res.status == GrindStatus.STUCK:
            status = Color.warning("[!!]")
        else:
            status = Color.error("[XX]")

        # Task name (truncated)
        task_short = task[:45] + "..." if len(task) > 48 else task

        # Metadata
        iters = f"{res.iterations}i"
        duration = format_duration(res.duration_seconds)
        meta = Color.dim(f"{iters:>3} {duration:>6}")

        print(f"  {status} {task_short:<48} {meta}")

    print(Color.dim("  " + "-" * 66))

    # Action items if any failures - show FULL details, no truncation
    if r.stuck or r.failed:
        print()
        print(Color.warning("  Action Required:"))
        for task, res in r.results:
            if res.status == GrindStatus.STUCK:
                print(Color.warning(f"    - STUCK: {task}"))
                if res.message:
                    print(Color.dim(f"      Reason: {res.message}"))
            elif res.status != GrindStatus.COMPLETE:
                print(Color.error(f"    - FAILED: {task}"))
                if res.message:
                        print(Color.dim(f"      Error: {res.message}"))

    print()
    print(Color.header("=" * 70))
