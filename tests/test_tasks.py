"""Tests for grind.tasks module."""

import json
import pytest
from pathlib import Path
from grind.tasks import parse_task_from_yaml, load_tasks
from grind.models import TaskDefinition


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
