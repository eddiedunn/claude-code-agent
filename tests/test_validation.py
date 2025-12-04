"""Tests for input validation and boundary testing."""

import pytest
from datetime import datetime

from grind.models import TaskDefinition
from grind.tui.core.models import AgentInfo, AgentType, AgentStatus


class TestTaskDefinitionValidation:
    """Tests for TaskDefinition validation."""

    def test_empty_task_description_rejected(self):
        """Test that TaskDefinition with empty task description is rejected."""
        task_def = TaskDefinition(task="", verify="echo test")
        errors = task_def.validate()
        assert len(errors) > 0
        assert any("Task description cannot be empty" in error for error in errors)

    def test_empty_verify_command_rejected(self):
        """Test that TaskDefinition with empty verify command is rejected."""
        task_def = TaskDefinition(task="test task", verify="")
        errors = task_def.validate()
        assert len(errors) > 0
        assert any("Verify command cannot be empty" in error for error in errors)

    def test_invalid_model_name_rejected(self):
        """Test that TaskDefinition with invalid model name is rejected."""
        task_def = TaskDefinition(
            task="test task",
            verify="echo test",
            model="gpt4"  # type: ignore
        )
        errors = task_def.validate()
        assert len(errors) > 0
        assert any("Invalid model" in error for error in errors)

    def test_negative_max_iterations_rejected(self):
        """Test that TaskDefinition with negative max_iterations is rejected."""
        task_def = TaskDefinition(
            task="test task",
            verify="echo test",
            max_iterations=-1
        )
        errors = task_def.validate()
        assert len(errors) > 0
        assert any("max_iterations must be >= 1" in error for error in errors)

    def test_zero_max_iterations_rejected(self):
        """Test that TaskDefinition with zero max_iterations is rejected."""
        task_def = TaskDefinition(
            task="test task",
            verify="echo test",
            max_iterations=0
        )
        errors = task_def.validate()
        assert len(errors) > 0
        assert any("max_iterations must be >= 1" in error for error in errors)


class TestAgentInfoValidation:
    """Tests for AgentInfo validation."""

    def test_negative_iteration_rejected(self):
        """Test that AgentInfo with negative iteration raises ValueError."""
        with pytest.raises(ValueError, match="iteration must be >= 0"):
            AgentInfo(
                agent_id="test_agent",
                task_id="task_1",
                task_description="Test task",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=-1,
                max_iterations=10,
                progress=0.0,
                created_at=datetime.now()
            )

    def test_zero_max_iterations_rejected(self):
        """Test that AgentInfo with zero max_iterations raises ValueError."""
        with pytest.raises(ValueError, match="max_iterations must be >= 1"):
            AgentInfo(
                agent_id="test_agent",
                task_id="task_1",
                task_description="Test task",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=0,
                max_iterations=0,
                progress=0.0,
                created_at=datetime.now()
            )

    def test_progress_below_zero_rejected(self):
        """Test that AgentInfo with progress < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="progress must be between 0.0 and 1.0"):
            AgentInfo(
                agent_id="test_agent",
                task_id="task_1",
                task_description="Test task",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=0,
                max_iterations=10,
                progress=-0.1,
                created_at=datetime.now()
            )

    def test_progress_above_one_rejected(self):
        """Test that AgentInfo with progress > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="progress must be between 0.0 and 1.0"):
            AgentInfo(
                agent_id="test_agent",
                task_id="task_1",
                task_description="Test task",
                agent_type=AgentType.WORKER,
                status=AgentStatus.RUNNING,
                model="sonnet",
                iteration=0,
                max_iterations=10,
                progress=1.1,
                created_at=datetime.now()
            )

    def test_task_description_truncation_at_100_chars(self):
        """Test that AgentInfo truncates task_description to 100 chars."""
        long_description = "a" * 150
        agent_info = AgentInfo(
            agent_id="test_agent",
            task_id="task_1",
            task_description=long_description,
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=0,
            max_iterations=10,
            progress=0.0,
            created_at=datetime.now()
        )
        assert len(agent_info.task_description) == 100
        assert agent_info.task_description == "a" * 100
