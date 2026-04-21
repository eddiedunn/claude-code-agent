"""grind compare — run the same task against multiple models in parallel worktrees.

For each model specified, a TaskDefinition is constructed with its own branch
name (``compare/<slug>/<sanitized_model_id>``), placed in an isolated git
worktree, and run via ``grind()``.  All runs fire concurrently via
``asyncio.gather``; each respects the per-run ``timeout`` if provided.

After all runs complete, a plain-text summary table is printed:

    model                      status    iterations  wall_time_s  note
    -----------------------------------------------------------------
    claude/sonnet              COMPLETE           3        42.1
    claude/opus                COMPLETE           2        91.7
    openrouter/openai/gpt-4o   ERROR              0         3.2   Provider error
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from grind.engine import grind
from grind.models import GrindResult, GrindStatus, TaskDefinition, WorktreeConfig
from grind.utils import Color
from grind.worktree import WorktreeManager


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    """Result for a single model run inside a compare session."""
    model: str
    status: GrindStatus | None = None
    iterations: int = 0
    wall_time_s: float = 0.0
    error: str = ""

    @property
    def status_label(self) -> str:
        if self.status is None:
            return "TIMEOUT"
        return self.status.value.upper()

    @property
    def ok(self) -> bool:
        return self.status == GrindStatus.COMPLETE


@dataclass
class CompareSession:
    """Parameters for a compare run."""
    task: str
    verify: str
    models: list[str]
    max_iterations: int = 10
    timeout: float | None = None          # per-model wall-clock timeout in seconds
    branch_prefix: str = "compare/"
    slug: str = ""                        # Optional short name for branch paths
    verbose: bool = False

    def __post_init__(self) -> None:
        if not self.slug:
            # Derive slug from first 30 chars of the task text, alphanumeric only
            raw = re.sub(r"[^a-z0-9]+", "-", self.task.lower())[:30].strip("-")
            self.slug = raw or "task"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_model(model_id: str) -> str:
    """Turn a model ID into a branch-safe string.

    Examples:
        "claude/sonnet"              → "claude-sonnet"
        "openrouter/openai/gpt-4o"   → "openrouter-openai-gpt-4o"
    """
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")


def _branch_name(prefix: str, slug: str, model_id: str) -> str:
    sanitized = _sanitize_model(model_id)
    # Ensure prefix ends with /
    if not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{slug}/{sanitized}"


def _task_id(slug: str, model_id: str) -> str:
    """Unique task-id used as the worktree directory name."""
    return f"{slug}-{_sanitize_model(model_id)}"


# ---------------------------------------------------------------------------
# Per-model runner
# ---------------------------------------------------------------------------

async def _run_one(
    session: CompareSession,
    model: str,
    worktree_manager: WorktreeManager,
) -> CompareResult:
    """Set up a worktree, run grind(), tear down — return a CompareResult."""
    branch = _branch_name(session.branch_prefix, session.slug, model)
    task_id = _task_id(session.slug, model)
    result = CompareResult(model=model)

    # --- create worktree ---
    try:
        worktree_path = await worktree_manager.create(task_id, branch)
    except Exception as exc:
        result.status = GrindStatus.ERROR
        result.error = f"Worktree setup failed: {exc}"
        return result

    task_def = TaskDefinition(
        task=session.task,
        verify=session.verify,
        max_iterations=session.max_iterations,
        model=model,
        cwd=str(worktree_path),
    )

    t0 = time.monotonic()
    try:
        coro = grind(task_def, verbose=session.verbose)
        if session.timeout:
            async with asyncio.timeout(session.timeout):
                grind_result: GrindResult = await coro
        else:
            grind_result = await coro
        result.status = grind_result.status
        result.iterations = grind_result.iterations
        result.wall_time_s = grind_result.duration_seconds or (time.monotonic() - t0)
    except asyncio.TimeoutError:
        result.status = None          # sentinel: timed out
        result.wall_time_s = time.monotonic() - t0
        result.error = f"Timed out after {session.timeout}s"
    except Exception as exc:
        result.status = GrindStatus.ERROR
        result.wall_time_s = time.monotonic() - t0
        result.error = str(exc)

    # --- cleanup worktree ---
    success = result.status == GrindStatus.COMPLETE
    worktree_cfg = WorktreeConfig(
        branch=branch,
        cleanup_on_success=True,
        cleanup_on_failure=False,
    )
    should_cleanup = success and worktree_cfg.cleanup_on_success or \
                     (not success and worktree_cfg.cleanup_on_failure)
    if should_cleanup:
        try:
            await worktree_manager.cleanup(task_id)
        except Exception:
            pass  # non-fatal

    return result


# ---------------------------------------------------------------------------
# Parallel fan-out
# ---------------------------------------------------------------------------

async def run_compare(session: CompareSession) -> list[CompareResult]:
    """Run all models in parallel, return a list of CompareResults in model order."""
    worktree_manager = WorktreeManager()

    coros = [_run_one(session, model, worktree_manager) for model in session.models]
    results: list[CompareResult] = await asyncio.gather(*coros, return_exceptions=False)
    return list(results)


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def render_table(results: list[CompareResult]) -> str:
    """Return a plain-text summary table as a string."""
    headers = ["model", "status", "iterations", "wall_time_s", "note"]
    rows: list[tuple[str, str, str, str, str]] = []
    for r in results:
        rows.append((
            r.model,
            r.status_label,
            str(r.iterations),
            f"{r.wall_time_s:.1f}",
            r.error or "",
        ))

    # Compute column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def _fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells))

    sep = "-" * (sum(col_widths) + 2 * (len(headers) - 1))
    lines = [
        _fmt_row(tuple(headers)),
        sep,
    ]
    for row in rows:
        lines.append(_fmt_row(row))

    return "\n".join(lines)


def print_compare_summary(results: list[CompareResult]) -> None:
    """Print the compare summary table to stdout with colour hints."""
    print()
    print(Color.header("=" * 60))
    print(Color.bold("COMPARE SUMMARY"))
    print(Color.header("=" * 60))
    print(render_table(results))
    print()

    complete = sum(1 for r in results if r.ok)
    total = len(results)
    summary = f"{complete}/{total} models completed successfully"
    if complete == total:
        print(Color.success(summary))
    elif complete > 0:
        print(Color.warning(summary))
    else:
        print(Color.error(summary))
    print()
