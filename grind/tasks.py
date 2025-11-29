import json
from pathlib import Path
from typing import Any

import yaml

from grind.models import (
    GrindHooks,
    PromptConfig,
    TaskDefinition,
    TaskGraph,
    TaskNode,
    WorktreeConfig,
)

# Default limits for task execution
DEFAULT_MAX_ITERATIONS = 10
DEFAULT_MAX_TURNS = 50


def parse_task_from_yaml(yaml_data: dict[str, Any]) -> TaskDefinition:
    hooks_data = yaml_data.get("hooks", {})
    hooks = GrindHooks(
        pre_grind=hooks_data.get("pre_grind", []),
        post_iteration=hooks_data.get("post_iteration", []),
        post_grind=hooks_data.get("post_grind", []),
    )
    hooks.normalize()

    prompt_data = yaml_data.get("prompt_config", {})
    prompt_config = PromptConfig(
        custom_prompt=prompt_data.get("custom_prompt"),
        preamble=prompt_data.get("preamble"),
        additional_rules=prompt_data.get("additional_rules", []),
        additional_context=prompt_data.get("additional_context"),
    )

    task_def = TaskDefinition(
        task=yaml_data["task"],
        verify=yaml_data["verify"],
        max_iterations=yaml_data.get("max_iterations", DEFAULT_MAX_ITERATIONS),
        cwd=yaml_data.get("cwd"),
        model=yaml_data.get("model", "sonnet"),
        hooks=hooks,
        prompt_config=prompt_config,
        allowed_tools=yaml_data.get("allowed_tools"),
        permission_mode=yaml_data.get("permission_mode", "acceptEdits"),
        max_turns=yaml_data.get("max_turns", DEFAULT_MAX_TURNS),
    )

    errors = task_def.validate()
    if errors:
        raise ValueError(f"Invalid task definition: {'; '.join(errors)}")

    return task_def


def load_tasks(path: str, base_cwd: str | None = None) -> list[TaskDefinition]:
    """Load tasks from a YAML or JSON file.

    Args:
        path: Path to the tasks file
        base_cwd: Base working directory for tasks. If not provided, defaults to
                  the parent directory of the tasks file. Individual task cwd
                  settings override this.
    """
    p = Path(path).resolve()
    content = p.read_text()
    data = yaml.safe_load(content) if p.suffix in (".yaml", ".yml") else json.loads(content)

    # Default base_cwd to tasks file's parent directory
    if base_cwd is None:
        base_cwd = str(p.parent)

    tasks = []
    for t in data.get("tasks", []):
        task_def = parse_task_from_yaml(t)
        # Only set cwd from base_cwd if task doesn't specify its own
        if task_def.cwd is None:
            task_def.cwd = base_cwd
        tasks.append(task_def)

    return tasks


def build_task_graph(path: str, base_cwd: str | None = None) -> TaskGraph:
    """Load tasks from YAML/JSON and build a TaskGraph with dependencies.

    This function extends load_tasks() to support task dependencies via
    the 'id' and 'depends_on' fields in the task file.

    Args:
        path: Path to the tasks file (YAML or JSON)
        base_cwd: Base working directory (defaults to tasks file's parent)

    Returns:
        TaskGraph with all tasks and their dependencies

    Raises:
        ValueError: If graph validation fails (cycles, missing deps)

    Example YAML:
        tasks:
          - id: lint
            task: "Fix linting"
            verify: "ruff check ."
          - id: test
            task: "Fix tests"
            verify: "pytest"
            depends_on: [lint]

    See docs/dag-execution-design.md for full format documentation.
    """
    p = Path(path).resolve()
    content = p.read_text()
    data = (
        yaml.safe_load(content)
        if p.suffix in (".yaml", ".yml")
        else json.loads(content)
    )

    if base_cwd is None:
        base_cwd = str(p.parent)

    nodes: dict[str, TaskNode] = {}

    for i, t in enumerate(data.get("tasks", []), 1):
        # Get or generate task ID
        task_id = t.get("id") or f"task_{i}"

        # Parse the task definition using existing function
        task_def = parse_task_from_yaml(t)
        if task_def.cwd is None:
            task_def.cwd = base_cwd

        # Get dependencies
        depends_on = t.get("depends_on", [])

        # Parse worktree config (supports two formats)
        worktree_config = None
        worktree_data = t.get("worktree", {})

        # Shorthand: branch at top level, or full worktree block
        branch = t.get("branch") or worktree_data.get("branch")

        if branch:
            worktree_config = WorktreeConfig(
                branch=branch,
                base_branch=worktree_data.get("base_branch", "HEAD"),
                merge_from=t.get("merge_from", worktree_data.get("merge_from", [])),
                cleanup_on_success=worktree_data.get("cleanup_on_success", True),
                cleanup_on_failure=worktree_data.get("cleanup_on_failure", False),
            )

        # Create node
        node = TaskNode(
            id=task_id,
            task_def=task_def,
            depends_on=depends_on,
            worktree=worktree_config,
        )
        nodes[task_id] = node

    graph = TaskGraph(nodes=nodes)

    # Validate the graph
    errors = graph.validate()
    if errors:
        raise ValueError(f"Invalid task graph: {'; '.join(errors)}")

    return graph
