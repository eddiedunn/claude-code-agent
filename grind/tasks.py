import json
from pathlib import Path

import yaml

from grind.models import GrindHooks, PromptConfig, TaskDefinition


def parse_task_from_yaml(yaml_data: dict) -> TaskDefinition:
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

    return TaskDefinition(
        task=yaml_data["task"],
        verify=yaml_data["verify"],
        max_iterations=yaml_data.get("max_iterations", 10),
        cwd=yaml_data.get("cwd"),
        model=yaml_data.get("model", "sonnet"),
        hooks=hooks,
        prompt_config=prompt_config,
        allowed_tools=yaml_data.get("allowed_tools"),
        permission_mode=yaml_data.get("permission_mode", "acceptEdits"),
        max_turns=yaml_data.get("max_turns", 50),
    )


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
