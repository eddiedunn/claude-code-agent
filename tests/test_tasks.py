"""Tests for grind.tasks module."""

import json

import pytest

from grind.models import TaskDefinition
from grind.tasks import build_task_graph, load_tasks, parse_task_from_yaml


class TestParseTaskFromYaml:
    def test_minimal_task(self):
        data = {
            "task": "Fix tests",
            "verify": "pytest"
        }
        task = parse_task_from_yaml(data)

        assert isinstance(task, TaskDefinition)
        assert task.task == "Fix tests"
        assert task.verify == "pytest"
        assert task.model == "sonnet"
        assert task.max_iterations == 10

    def test_task_with_model(self):
        data = {
            "task": "Fix linting",
            "verify": "ruff check .",
            "model": "haiku",
            "max_iterations": 5
        }
        task = parse_task_from_yaml(data)

        assert task.model == "haiku"
        assert task.max_iterations == 5

    def test_task_with_hooks(self):
        data = {
            "task": "Complex task",
            "verify": "pytest",
            "hooks": {
                "pre_grind": ["/compact"],
                "post_iteration": ["/test"],
                "post_grind": ["/review"]
            }
        }
        task = parse_task_from_yaml(data)

        assert len(task.hooks.pre_grind) == 1
        assert len(task.hooks.post_iteration) == 1
        assert len(task.hooks.post_grind) == 1

    def test_task_with_prompt_config(self):
        data = {
            "task": "Security audit",
            "verify": "bandit -r src/",
            "prompt_config": {
                "preamble": "You are a security expert.",
                "additional_rules": ["Check for SQL injection", "Verify input sanitization"],
                "additional_context": "Focus on authentication"
            }
        }
        task = parse_task_from_yaml(data)

        assert task.prompt_config.preamble == "You are a security expert."
        assert len(task.prompt_config.additional_rules) == 2
        assert task.prompt_config.additional_context == "Focus on authentication"

    def test_task_with_all_options(self):
        data = {
            "task": "Full featured task",
            "verify": "pytest -v",
            "max_iterations": 15,
            "cwd": "/tmp/project",
            "model": "opus",
            "hooks": {"pre_grind": ["/compact"]},
            "prompt_config": {"preamble": "Expert mode"},
            "allowed_tools": ["Read", "Write"],
            "permission_mode": "requireApproval",
            "max_turns": 100
        }
        task = parse_task_from_yaml(data)

        assert task.task == "Full featured task"
        assert task.max_iterations == 15
        assert task.cwd == "/tmp/project"
        assert task.model == "opus"
        assert task.allowed_tools == ["Read", "Write"]
        assert task.permission_mode == "requireApproval"
        assert task.max_turns == 100

    def test_parse_invalid_empty_task_raises_error(self):
        data = {"task": "", "verify": "pytest"}
        with pytest.raises(ValueError) as exc_info:
            parse_task_from_yaml(data)
        assert "Task description cannot be empty" in str(exc_info.value)

    def test_parse_invalid_empty_verify_raises_error(self):
        data = {"task": "Fix tests", "verify": ""}
        with pytest.raises(ValueError) as exc_info:
            parse_task_from_yaml(data)
        assert "Verify command cannot be empty" in str(exc_info.value)

    def test_parse_invalid_model_raises_error(self):
        data = {"task": "Fix tests", "verify": "pytest", "model": "invalid"}
        with pytest.raises(ValueError) as exc_info:
            parse_task_from_yaml(data)
        assert "Invalid model: invalid" in str(exc_info.value)

    def test_parse_invalid_max_iterations_raises_error(self):
        data = {"task": "Fix tests", "verify": "pytest", "max_iterations": 0}
        with pytest.raises(ValueError) as exc_info:
            parse_task_from_yaml(data)
        assert "max_iterations must be >= 1" in str(exc_info.value)


class TestLoadTasks:
    def test_load_yaml_file(self, tmp_path):
        task_file = tmp_path / "tasks.yaml"
        content = """
tasks:
  - task: "Task 1"
    verify: "echo 1"
    model: haiku
  - task: "Task 2"
    verify: "echo 2"
    model: sonnet
"""
        task_file.write_text(content)

        tasks = load_tasks(str(task_file))

        assert len(tasks) == 2
        assert tasks[0].task == "Task 1"
        assert tasks[0].model == "haiku"
        assert tasks[1].task == "Task 2"
        assert tasks[1].model == "sonnet"

    def test_load_json_file(self, tmp_path):
        task_file = tmp_path / "tasks.json"
        content = {
            "tasks": [
                {"task": "Task 1", "verify": "echo 1", "model": "haiku"},
                {"task": "Task 2", "verify": "echo 2", "model": "sonnet"}
            ]
        }
        task_file.write_text(json.dumps(content))

        tasks = load_tasks(str(task_file))

        assert len(tasks) == 2
        assert tasks[0].task == "Task 1"
        assert tasks[1].task == "Task 2"

    def test_load_yml_extension(self, tmp_path):
        task_file = tmp_path / "tasks.yml"
        content = """
tasks:
  - task: "Test task"
    verify: "pytest"
"""
        task_file.write_text(content)

        tasks = load_tasks(str(task_file))

        assert len(tasks) == 1
        assert tasks[0].task == "Test task"

    def test_empty_tasks_list(self, tmp_path):
        task_file = tmp_path / "tasks.yaml"
        content = "tasks: []"
        task_file.write_text(content)

        tasks = load_tasks(str(task_file))

        assert len(tasks) == 0


def write_yaml(tmp_path, content: str) -> str:
    """Write YAML content to a temp file and return path."""
    f = tmp_path / "tasks.yaml"
    f.write_text(content)
    return str(f)


class TestBuildTaskGraph:
    def test_build_task_graph_simple(self, tmp_path):
        """Tasks without IDs get auto-generated IDs."""
        yaml_content = """
tasks:
  - task: "Task A"
    verify: "echo a"
  - task: "Task B"
    verify: "echo b"
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        assert len(graph.nodes) == 2
        assert "task_1" in graph.nodes
        assert "task_2" in graph.nodes

    def test_build_task_graph_with_explicit_ids(self, tmp_path):
        """Tasks with explicit IDs use those IDs."""
        yaml_content = """
tasks:
  - id: lint
    task: "Fix lint"
    verify: "ruff check ."
  - id: test
    task: "Fix tests"
    verify: "pytest"
    depends_on: [lint]
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        assert "lint" in graph.nodes
        assert "test" in graph.nodes
        assert graph.nodes["test"].depends_on == ["lint"]

    def test_build_task_graph_validates_cycle(self, tmp_path):
        """Should raise ValueError on cycle detection."""
        yaml_content = """
tasks:
  - id: a
    task: "A"
    verify: "echo a"
    depends_on: [b]
  - id: b
    task: "B"
    verify: "echo b"
    depends_on: [a]
"""
        path = write_yaml(tmp_path, yaml_content)

        with pytest.raises(ValueError, match="[Cc]ycle"):
            build_task_graph(path)

    def test_build_task_graph_validates_missing_dep(self, tmp_path):
        """Should raise ValueError on missing dependency."""
        yaml_content = """
tasks:
  - id: a
    task: "A"
    verify: "echo a"
    depends_on: [nonexistent]
"""
        path = write_yaml(tmp_path, yaml_content)

        with pytest.raises(ValueError, match="non-existent|nonexistent"):
            build_task_graph(path)

    def test_build_task_graph_sets_cwd(self, tmp_path):
        """Tasks should get cwd set to file's parent directory."""
        yaml_content = """
tasks:
  - task: "A"
    verify: "echo a"
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        assert graph.nodes["task_1"].task_def.cwd == str(tmp_path)

    def test_build_task_graph_branch_shorthand(self, tmp_path):
        """Shorthand branch syntax creates WorktreeConfig."""
        yaml_content = """
tasks:
  - id: lint
    task: "Fix lint"
    verify: "ruff check ."
    branch: fix/lint
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        node = graph.nodes["lint"]
        assert node.worktree is not None
        assert node.worktree.branch == "fix/lint"
        assert node.worktree.base_branch == "HEAD"  # Default

    def test_build_task_graph_full_worktree_config(self, tmp_path):
        """Full worktree config parses all fields."""
        yaml_content = """
tasks:
  - id: test
    task: "Fix tests"
    verify: "pytest"
    worktree:
      branch: fix/tests
      base_branch: main
      merge_from: [fix/lint]
      cleanup_on_success: false
      cleanup_on_failure: true
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        node = graph.nodes["test"]
        assert node.worktree is not None
        assert node.worktree.branch == "fix/tests"
        assert node.worktree.base_branch == "main"
        assert node.worktree.merge_from == ["fix/lint"]
        assert node.worktree.cleanup_on_success is False
        assert node.worktree.cleanup_on_failure is True

    def test_build_task_graph_merge_from_shorthand(self, tmp_path):
        """merge_from can be at task level."""
        yaml_content = """
tasks:
  - id: b
    task: "B"
    verify: "echo b"
    branch: fix/b
    merge_from: [fix/a]
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        assert graph.nodes["b"].worktree.merge_from == ["fix/a"]

    def test_build_task_graph_no_worktree(self, tmp_path):
        """Tasks without branch/worktree have None worktree."""
        yaml_content = """
tasks:
  - id: simple
    task: "Simple task"
    verify: "echo ok"
"""
        path = write_yaml(tmp_path, yaml_content)

        graph = build_task_graph(path)

        assert graph.nodes["simple"].worktree is None
