"""Tests for grind.orchestration.agent and grind.orchestration.grind_agent modules."""

from unittest.mock import AsyncMock, patch

import pytest

from grind.models import GrindResult, GrindStatus, TaskDefinition
from grind.orchestration.agent import Agent, AgentResult, AgentStatus
from grind.orchestration.grind_agent import GrindAgent


class TestAgentStatus:
    """Test AgentStatus enum."""

    def test_enum_values(self):
        """AgentStatus should have correct string values."""
        assert AgentStatus.COMPLETE.value == "complete"
        assert AgentStatus.STUCK.value == "stuck"
        assert AgentStatus.MAX_ITERATIONS.value == "max_iterations"
        assert AgentStatus.ERROR.value == "error"


class TestAgentResult:
    """Test AgentResult dataclass."""

    def test_creation_minimal(self):
        """AgentResult should work with minimal required fields."""
        result = AgentResult(
            status=AgentStatus.COMPLETE,
            iterations=3
        )

        assert result.status == AgentStatus.COMPLETE
        assert result.iterations == 3
        assert result.output == {}
        assert result.message == ""
        assert result.duration_seconds == 0.0

    def test_creation_full(self):
        """AgentResult should store all provided fields."""
        result = AgentResult(
            status=AgentStatus.COMPLETE,
            iterations=5,
            output={"result": "success", "tools": ["Read", "Write"]},
            message="Task completed successfully",
            duration_seconds=12.5
        )

        assert result.status == AgentStatus.COMPLETE
        assert result.iterations == 5
        assert result.output == {"result": "success", "tools": ["Read", "Write"]}
        assert result.message == "Task completed successfully"
        assert result.duration_seconds == 12.5

    def test_different_statuses(self):
        """AgentResult should support all status types."""
        for status in [AgentStatus.COMPLETE, AgentStatus.STUCK,
                      AgentStatus.MAX_ITERATIONS, AgentStatus.ERROR]:
            result = AgentResult(status=status, iterations=1)
            assert result.status == status


class TestAgentProtocol:
    """Test Agent protocol conformance."""

    @pytest.mark.asyncio
    async def test_simple_agent_implementation(self):
        """A simple class with async run() should conform to Agent protocol."""

        class SimpleAgent:
            async def run(self, input: dict[str, object]) -> AgentResult:
                return AgentResult(
                    status=AgentStatus.COMPLETE,
                    iterations=1,
                    output={"processed": input}
                )

        agent: Agent = SimpleAgent()
        result = await agent.run({"task": "test"})

        assert result.status == AgentStatus.COMPLETE
        assert result.iterations == 1
        assert result.output == {"processed": {"task": "test"}}


class TestGrindAgent:
    """Test GrindAgent wrapper."""

    @pytest.mark.asyncio
    async def test_missing_task_parameter(self):
        """GrindAgent should return ERROR when task is missing."""
        agent = GrindAgent()

        result = await agent.run({"verify": "pytest"})

        assert result.status == AgentStatus.ERROR
        assert result.iterations == 0
        assert "task" in result.message.lower()

    @pytest.mark.asyncio
    async def test_missing_verify_parameter(self):
        """GrindAgent should return ERROR when verify is missing."""
        agent = GrindAgent()

        result = await agent.run({"task": "Test task"})

        assert result.status == AgentStatus.ERROR
        assert result.iterations == 0
        assert "verify" in result.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_task_type(self):
        """GrindAgent should return ERROR when task is not a string."""
        agent = GrindAgent()

        result = await agent.run({"task": 123, "verify": "pytest"})

        assert result.status == AgentStatus.ERROR
        assert result.iterations == 0
        assert "task" in result.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_verify_type(self):
        """GrindAgent should return ERROR when verify is not a string."""
        agent = GrindAgent()

        result = await agent.run({"task": "Test", "verify": None})

        assert result.status == AgentStatus.ERROR
        assert result.iterations == 0
        assert "verify" in result.message.lower()

    @pytest.mark.asyncio
    async def test_successful_grind_complete(self):
        """GrindAgent should convert COMPLETE status correctly."""
        agent = GrindAgent()

        # Mock the grind function
        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="All tests passed",
            tools_used=["Read", "Write", "Bash"],
            duration_seconds=10.5,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Fix the tests",
                "verify": "pytest"
            })

        assert result.status == AgentStatus.COMPLETE
        assert result.iterations == 3
        assert result.message == "All tests passed"
        assert result.duration_seconds == 10.5
        assert result.output["tools_used"] == ["Read", "Write", "Bash"]
        assert result.output["model"] == "sonnet"

    @pytest.mark.asyncio
    async def test_grind_stuck_status(self):
        """GrindAgent should convert STUCK status correctly."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.STUCK,
            iterations=5,
            message="GRIND_STUCK: Cannot proceed",
            tools_used=["Read"],
            duration_seconds=15.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Complex task",
                "verify": "pytest"
            })

        assert result.status == AgentStatus.STUCK
        assert result.iterations == 5
        assert "Cannot proceed" in result.message

    @pytest.mark.asyncio
    async def test_grind_max_iterations_status(self):
        """GrindAgent should convert MAX_ITERATIONS status correctly."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.MAX_ITERATIONS,
            iterations=10,
            message="Reached maximum iterations",
            tools_used=["Read", "Write"],
            duration_seconds=30.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Long task",
                "verify": "pytest",
                "max_iterations": 10
            })

        assert result.status == AgentStatus.MAX_ITERATIONS
        assert result.iterations == 10

    @pytest.mark.asyncio
    async def test_grind_error_status(self):
        """GrindAgent should convert ERROR status correctly."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.ERROR,
            iterations=1,
            message="Verification command failed",
            tools_used=[],
            duration_seconds=2.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Task",
                "verify": "invalid_command"
            })

        assert result.status == AgentStatus.ERROR
        assert result.iterations == 1
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_optional_parameters_passed_through(self):
        """GrindAgent should pass optional parameters to TaskDefinition."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="opus"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)) as mock_grind:
            result = await agent.run({
                "task": "Test",
                "verify": "pytest",
                "max_iterations": 7,
                "model": "opus",
                "cwd": "/tmp",
                "allowed_tools": ["Read", "Write"],
                "permission_mode": "requireApproval"
            })

            # Verify TaskDefinition was created with correct parameters
            call_args = mock_grind.call_args
            task_def: TaskDefinition = call_args[0][0]

            assert task_def.task == "Test"
            assert task_def.verify == "pytest"
            assert task_def.max_iterations == 7
            assert task_def.model == "opus"
            assert task_def.cwd == "/tmp"
            assert task_def.allowed_tools == ["Read", "Write"]
            assert task_def.permission_mode == "requireApproval"

    @pytest.mark.asyncio
    async def test_verbose_flag_passed_through(self):
        """GrindAgent should pass verbose flag to grind()."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)) as mock_grind:
            result = await agent.run({
                "task": "Test",
                "verify": "pytest",
                "verbose": True
            })

            # Verify verbose flag was passed
            call_args = mock_grind.call_args
            assert call_args[1]["verbose"] is True

    @pytest.mark.asyncio
    async def test_default_max_iterations(self):
        """GrindAgent should use default max_iterations of 5."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)) as mock_grind:
            result = await agent.run({
                "task": "Test",
                "verify": "pytest"
            })

            # Verify default max_iterations
            call_args = mock_grind.call_args
            task_def: TaskDefinition = call_args[0][0]
            assert task_def.max_iterations == 5

    @pytest.mark.asyncio
    async def test_output_dict_structure(self):
        """GrindAgent should populate output dict with grind result data."""
        agent = GrindAgent()

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=2,
            message="Success message",
            tools_used=["Read", "Write", "Bash"],
            duration_seconds=12.5,
            hooks_executed=[("/test", "output", True)],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Test",
                "verify": "pytest"
            })

        # Verify output dict structure
        assert "message" in result.output
        assert "tools_used" in result.output
        assert "duration_seconds" in result.output
        assert "model" in result.output
        assert "hooks_executed" in result.output

        assert result.output["message"] == "Success message"
        assert result.output["tools_used"] == ["Read", "Write", "Bash"]
        assert result.output["duration_seconds"] == 12.5
        assert result.output["model"] == "sonnet"
        assert result.output["hooks_executed"] == [("/test", "output", True)]

    @pytest.mark.asyncio
    async def test_grind_agent_conforms_to_protocol(self):
        """GrindAgent should conform to Agent protocol."""
        agent: Agent = GrindAgent()

        # Should have run method
        assert hasattr(agent, 'run')
        assert callable(agent.run)

        # run should be async and return AgentResult
        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await agent.run({
                "task": "Test",
                "verify": "pytest"
            })

        assert isinstance(result, AgentResult)
