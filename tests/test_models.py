"""Tests for grind.models module."""

import pytest
from grind.models import (
    HookTrigger,
    SlashCommandHook,
    GrindHooks,
    PromptConfig,
    GrindStatus,
    GrindResult,
    TaskDefinition,
    BatchResult,
)


class TestHookTrigger:
    def test_enum_values(self):
        assert HookTrigger.EVERY.value == "every"
        assert HookTrigger.EVERY_N.value == "every_n"
        assert HookTrigger.ON_ERROR.value == "on_error"
        assert HookTrigger.ON_SUCCESS.value == "on_success"
        assert HookTrigger.ONCE.value == "once"


class TestSlashCommandHook:
    def test_should_run_once(self):
        hook = SlashCommandHook("/test", trigger="once")
        assert hook.should_run(1, False) is True
        assert hook.should_run(2, False) is False
        assert hook.should_run(3, False) is False

    def test_should_run_every(self):
        hook = SlashCommandHook("/test", trigger="every")
        assert hook.should_run(1, False) is True
        assert hook.should_run(2, False) is True
        assert hook.should_run(10, False) is True

    def test_should_run_every_n(self):
        hook = SlashCommandHook("/test", trigger="every_n", trigger_count=3)
        assert hook.should_run(1, False) is False
        assert hook.should_run(2, False) is False
        assert hook.should_run(3, False) is True
        assert hook.should_run(4, False) is False
        assert hook.should_run(6, False) is True

    def test_should_run_on_error(self):
        hook = SlashCommandHook("/test", trigger="on_error")
        assert hook.should_run(1, is_error=False) is False
        assert hook.should_run(1, is_error=True) is True
        assert hook.should_run(5, is_error=True) is True

    def test_trigger_string_conversion(self):
        hook = SlashCommandHook("/test", trigger="every")
        assert hook.trigger == HookTrigger.EVERY

    def test_invalid_trigger_defaults_to_once(self):
        hook = SlashCommandHook("/test", trigger="invalid")
        assert hook.trigger == HookTrigger.ONCE


class TestGrindHooks:
    def test_normalize_string_commands(self):
        hooks = GrindHooks(
            pre_grind=["/compact"],
            post_iteration=["/test"],
            post_grind=["/review"]
        )
        hooks.normalize()

        assert isinstance(hooks.pre_grind[0], SlashCommandHook)
        assert hooks.pre_grind[0].command == "/compact"
        assert isinstance(hooks.post_iteration[0], SlashCommandHook)
        assert isinstance(hooks.post_grind[0], SlashCommandHook)

    def test_normalize_mixed_types(self):
        hook_obj = SlashCommandHook("/test", trigger="every")
        hooks = GrindHooks(
            pre_grind=["/compact", hook_obj],
        )
        hooks.normalize()

        assert len(hooks.pre_grind) == 2
        assert isinstance(hooks.pre_grind[0], SlashCommandHook)
        assert isinstance(hooks.pre_grind[1], SlashCommandHook)
        assert hooks.pre_grind[1].trigger == HookTrigger.EVERY


class TestPromptConfig:
    def test_defaults(self):
        config = PromptConfig()
        assert config.custom_prompt is None
        assert config.preamble is None
        assert config.additional_rules == []
        assert config.additional_context is None


class TestGrindStatus:
    def test_enum_values(self):
        assert GrindStatus.COMPLETE.value == "complete"
        assert GrindStatus.STUCK.value == "stuck"
        assert GrindStatus.MAX_ITERATIONS.value == "max_iterations"
        assert GrindStatus.ERROR.value == "error"


class TestGrindResult:
    def test_creation(self):
        result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=5,
            message="Success",
            tools_used=["Read", "Write"],
            duration_seconds=10.5,
            hooks_executed=[("/test", "output", True)],
            model="sonnet"
        )

        assert result.status == GrindStatus.COMPLETE
        assert result.iterations == 5
        assert result.message == "Success"
        assert result.tools_used == ["Read", "Write"]
        assert result.duration_seconds == 10.5
        assert len(result.hooks_executed) == 1
        assert result.model == "sonnet"


class TestTaskDefinition:
    def test_creation_minimal(self):
        task = TaskDefinition(
            task="Fix tests",
            verify="pytest"
        )

        assert task.task == "Fix tests"
        assert task.verify == "pytest"
        assert task.model == "sonnet"
        assert task.max_iterations == 10
        assert task.cwd is None

    def test_creation_full(self):
        hooks = GrindHooks(pre_grind=["/compact"])
        prompt_config = PromptConfig(preamble="Test preamble")

        task = TaskDefinition(
            task="Complex task",
            verify="pytest -v",
            model="opus",
            max_iterations=20,
            cwd="/tmp",
            hooks=hooks,
            prompt_config=prompt_config,
            allowed_tools=["Read", "Write"],
            permission_mode="requireApproval",
            max_turns=100
        )

        assert task.task == "Complex task"
        assert task.model == "opus"
        assert task.max_iterations == 20
        assert task.cwd == "/tmp"
        assert task.hooks == hooks
        assert task.prompt_config == prompt_config
        assert task.allowed_tools == ["Read", "Write"]
        assert task.permission_mode == "requireApproval"
        assert task.max_turns == 100

    def test_validate_empty_task_fails(self):
        task = TaskDefinition(task="", verify="pytest")
        errors = task.validate()
        assert len(errors) == 1
        assert "Task description cannot be empty" in errors[0]

    def test_validate_empty_verify_fails(self):
        task = TaskDefinition(task="Fix tests", verify="")
        errors = task.validate()
        assert len(errors) == 1
        assert "Verify command cannot be empty" in errors[0]

    def test_validate_invalid_model_fails(self):
        task = TaskDefinition(task="Fix tests", verify="pytest", model="invalid")
        errors = task.validate()
        assert len(errors) == 1
        assert "Invalid model: invalid" in errors[0]

    def test_validate_negative_iterations_fails(self):
        task = TaskDefinition(task="Fix tests", verify="pytest", max_iterations=0)
        errors = task.validate()
        assert len(errors) == 1
        assert "max_iterations must be >= 1" in errors[0]

    def test_validate_valid_task_passes(self):
        task = TaskDefinition(task="Fix tests", verify="pytest")
        errors = task.validate()
        assert len(errors) == 0


class TestBatchResult:
    def test_creation(self):
        results = [
            ("Task 1", GrindResult(GrindStatus.COMPLETE, 3, "", [], 10.0, [], "sonnet")),
            ("Task 2", GrindResult(GrindStatus.STUCK, 5, "Error", [], 15.0, [], "sonnet")),
        ]

        batch = BatchResult(
            total=2,
            completed=1,
            stuck=1,
            failed=0,
            results=results,
            duration_seconds=25.0
        )

        assert batch.total == 2
        assert batch.completed == 1
        assert batch.stuck == 1
        assert batch.failed == 0
        assert len(batch.results) == 2
        assert batch.duration_seconds == 25.0
