"""Tests for fusion mode components."""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from grind.fusion import FusionExecutor, generate_session_id, list_sessions
from grind.fusion_prompts import build_fusion_prompt, parse_fusion_response
from grind.models import (
    AgentOutput,
    FusionConfig,
    FusionDecision,
    GrindResult,
    GrindStatus,
)


# ============================================================================
# Model Tests
# ============================================================================


class TestFusionConfig:
    """Tests for FusionConfig model."""

    def test_fusion_config_defaults(self):
        """FusionConfig should have sensible defaults."""
        config = FusionConfig(prompt="Fix bug", verify="pytest")

        assert config.prompt == "Fix bug"
        assert config.verify == "pytest"
        assert config.agent_count == 3
        assert config.strategy == "best-pick"
        assert config.model == "sonnet"
        assert config.fusion_model == "opus"
        assert config.max_iterations == 10
        assert config.timeout_seconds == 600

    def test_fusion_config_validation(self):
        """FusionConfig should validate all fields."""
        # Empty prompt
        config = FusionConfig(prompt="", verify="pytest")
        errors = config.validate()
        assert len(errors) == 1
        assert "Prompt cannot be empty" in errors[0]

        # Empty verify
        config = FusionConfig(prompt="Fix bug", verify="")
        errors = config.validate()
        assert len(errors) == 1
        assert "Verify command cannot be empty" in errors[0]

        # Invalid agent_count
        config = FusionConfig(prompt="Fix bug", verify="pytest", agent_count=0)
        errors = config.validate()
        assert len(errors) == 1
        assert "agent_count must be >= 1" in errors[0]

        # Invalid strategy
        config = FusionConfig(prompt="Fix bug", verify="pytest", strategy="invalid")
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid strategy" in errors[0]

        # Invalid model
        config = FusionConfig(prompt="Fix bug", verify="pytest", model="invalid")
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid model" in errors[0]

        # Invalid fusion_model
        config = FusionConfig(prompt="Fix bug", verify="pytest", fusion_model="invalid")
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid fusion_model" in errors[0]

        # Invalid max_iterations
        config = FusionConfig(prompt="Fix bug", verify="pytest", max_iterations=0)
        errors = config.validate()
        assert len(errors) == 1
        assert "max_iterations must be >= 1" in errors[0]

        # Invalid timeout_seconds
        config = FusionConfig(prompt="Fix bug", verify="pytest", timeout_seconds=0)
        errors = config.validate()
        assert len(errors) == 1
        assert "timeout_seconds must be >= 1" in errors[0]

        # Valid config
        config = FusionConfig(prompt="Fix bug", verify="pytest")
        errors = config.validate()
        assert len(errors) == 0


class TestAgentOutput:
    """Tests for AgentOutput model."""

    def test_agent_output_serialization(self):
        """AgentOutput should be serializable with all fields."""
        result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=5,
            message="Success",
            tools_used=["Read", "Write"],
            duration_seconds=10.5,
            model="sonnet",
        )

        output = AgentOutput(
            agent_id="agent-0",
            worktree_branch="fuse/session-123/agent-0",
            result=result,
            diff="+ new line\n- old line",
            files_changed=["file1.py", "file2.py"],
            summary="Fixed the bug",
        )

        assert output.agent_id == "agent-0"
        assert output.worktree_branch == "fuse/session-123/agent-0"
        assert output.result.status == GrindStatus.COMPLETE
        assert output.diff == "+ new line\n- old line"
        assert output.files_changed == ["file1.py", "file2.py"]
        assert output.summary == "Fixed the bug"


class TestFusionDecision:
    """Tests for FusionDecision model."""

    def test_fusion_decision_fields(self):
        """FusionDecision should have all required fields."""
        decision = FusionDecision(
            strategy_used="best-pick",
            selected_agents=["agent-1"],
            reasoning="Agent 1 had the cleanest solution",
            confidence=0.95,
            hybrid_instructions=None,
        )

        assert decision.strategy_used == "best-pick"
        assert decision.selected_agents == ["agent-1"]
        assert decision.reasoning == "Agent 1 had the cleanest solution"
        assert decision.confidence == 0.95
        assert decision.hybrid_instructions is None

        # Test hybrid with instructions
        decision = FusionDecision(
            strategy_used="hybrid",
            selected_agents=["agent-0", "agent-1"],
            reasoning="Combine file handling from agent-0 with logic from agent-1",
            confidence=0.85,
            hybrid_instructions={"agent-0": ["file1.py"], "agent-1": ["file2.py"]},
        )

        assert decision.strategy_used == "hybrid"
        assert len(decision.selected_agents) == 2
        assert decision.hybrid_instructions is not None
        assert "agent-0" in decision.hybrid_instructions


# ============================================================================
# Prompt Tests
# ============================================================================


class TestBuildFusionPrompt:
    """Tests for build_fusion_prompt function."""

    def test_build_fusion_prompt_single_agent(self):
        """Should build prompt with single agent output."""
        config = FusionConfig(
            prompt="Fix the bug",
            verify="pytest",
            strategy="best-pick",
        )

        result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="Fixed",
            tools_used=["Edit"],
            duration_seconds=5.0,
            model="sonnet",
        )

        agent_outputs = {
            "agent-0": AgentOutput(
                agent_id="agent-0",
                worktree_branch="fuse/test/agent-0",
                result=result,
                diff="+ fixed line",
                files_changed=["bug.py"],
                summary="Fixed the bug",
            )
        }

        prompt = build_fusion_prompt(config, agent_outputs)

        assert "Fix the bug" in prompt
        assert "pytest" in prompt
        assert "agent-0" in prompt
        assert "Fixed the bug" in prompt
        assert "best-pick" in prompt
        assert "bug.py" in prompt

    def test_build_fusion_prompt_multiple_agents(self):
        """Should build prompt with multiple agent outputs."""
        config = FusionConfig(
            prompt="Implement feature X",
            verify="pytest tests/",
            strategy="hybrid",
            agent_count=2,
        )

        result1 = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=5,
            message="Done",
            tools_used=["Write"],
            duration_seconds=10.0,
            model="sonnet",
        )

        result2 = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=4,
            message="Complete",
            tools_used=["Edit"],
            duration_seconds=8.0,
            model="sonnet",
        )

        agent_outputs = {
            "agent-0": AgentOutput(
                agent_id="agent-0",
                worktree_branch="fuse/test/agent-0",
                result=result1,
                diff="+ implementation 1",
                files_changed=["feature.py"],
                summary="Implemented feature using approach A",
            ),
            "agent-1": AgentOutput(
                agent_id="agent-1",
                worktree_branch="fuse/test/agent-1",
                result=result2,
                diff="+ implementation 2",
                files_changed=["feature.py", "utils.py"],
                summary="Implemented feature using approach B",
            ),
        }

        prompt = build_fusion_prompt(config, agent_outputs)

        assert "Implement feature X" in prompt
        assert "pytest tests/" in prompt
        assert "agent-0" in prompt
        assert "agent-1" in prompt
        assert "hybrid" in prompt
        assert "approach A" in prompt
        assert "approach B" in prompt


class TestParseFusionResponse:
    """Tests for parse_fusion_response function."""

    def test_parse_fusion_response_valid(self):
        """Should parse valid JSON response."""
        response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-1"],
            "reasoning": "Agent 1 has the cleanest and most maintainable solution.",
            "confidence": 0.90,
            "hybrid_instructions": None,
        })

        decision = parse_fusion_response(response)

        assert decision.strategy_used == "best-pick"
        assert decision.selected_agents == ["agent-1"]
        assert "cleanest" in decision.reasoning
        assert decision.confidence == 0.90
        assert decision.hybrid_instructions is None

    def test_parse_fusion_response_with_markdown(self):
        """Should parse JSON from markdown code block."""
        response = """Here is my decision:

```json
{
    "decision": "hybrid",
    "selected_agents": ["agent-0", "agent-2"],
    "reasoning": "Combining agent-0's error handling with agent-2's implementation.",
    "confidence": 0.85,
    "hybrid_instructions": {
        "agent-0": ["error_handler.py"],
        "agent-2": ["main.py", "utils.py"]
    }
}
```

This is the best approach.
"""

        decision = parse_fusion_response(response)

        assert decision.strategy_used == "hybrid"
        assert len(decision.selected_agents) == 2
        assert decision.confidence == 0.85
        assert decision.hybrid_instructions is not None
        assert "agent-0" in decision.hybrid_instructions

    def test_parse_fusion_response_invalid_json(self):
        """Should raise ValueError for invalid JSON."""
        response = "This is not JSON at all"

        with pytest.raises(ValueError, match="No JSON object found"):
            parse_fusion_response(response)

    def test_parse_fusion_response_missing_fields(self):
        """Should raise ValueError for missing required fields."""
        # Missing 'reasoning'
        response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-1"],
            "confidence": 0.90,
        })

        with pytest.raises(ValueError, match="Missing required fields"):
            parse_fusion_response(response)

        # Missing 'confidence'
        response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-1"],
            "reasoning": "Good solution",
        })

        with pytest.raises(ValueError, match="Missing required fields"):
            parse_fusion_response(response)

    def test_parse_fusion_response_invalid_decision(self):
        """Should raise ValueError for invalid decision value."""
        response = json.dumps({
            "decision": "invalid-decision",
            "selected_agents": ["agent-1"],
            "reasoning": "Some reasoning here",
            "confidence": 0.90,
        })

        with pytest.raises(ValueError, match="Invalid decision"):
            parse_fusion_response(response)

    def test_parse_fusion_response_invalid_confidence(self):
        """Should raise ValueError for confidence out of range."""
        response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-1"],
            "reasoning": "Good solution with confidence",
            "confidence": 1.5,  # Invalid: > 1.0
        })

        with pytest.raises(ValueError, match="confidence must be a number between 0.0 and 1.0"):
            parse_fusion_response(response)

    def test_parse_fusion_response_short_reasoning(self):
        """Should raise ValueError for reasoning too short."""
        response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-1"],
            "reasoning": "Good",  # Too short
            "confidence": 0.90,
        })

        with pytest.raises(ValueError, match="reasoning must be at least 10 characters"):
            parse_fusion_response(response)


# ============================================================================
# Executor Tests (with mocking)
# ============================================================================


class TestGenerateSessionId:
    """Tests for generate_session_id function."""

    def test_generate_session_id_format(self):
        """Session ID should have correct format."""
        session_id = generate_session_id()

        assert session_id.startswith("fuse_")
        assert len(session_id) == len("fuse_") + 8  # fuse_ + 8 hex chars

        # Verify it's hexadecimal after the prefix
        hex_part = session_id[5:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_generate_session_id_unique(self):
        """Should generate unique IDs."""
        ids = [generate_session_id() for _ in range(100)]
        assert len(ids) == len(set(ids))  # All unique


class TestFusionExecutor:
    """Tests for FusionExecutor class."""

    @pytest.mark.asyncio
    async def test_setup_worktrees_creates_branches(self):
        """Should create worktrees with correct branch names."""
        config = FusionConfig(
            prompt="Test task",
            verify="true",
            agent_count=2,
        )

        executor = FusionExecutor(config)

        # Mock the worktree manager
        executor.worktree_manager.create = AsyncMock(return_value="/tmp/worktree")

        worktree_paths = await executor._setup_worktrees()

        assert len(worktree_paths) == 2
        assert "agent-0" in worktree_paths
        assert "agent-1" in worktree_paths

        # Verify create was called with correct arguments
        assert executor.worktree_manager.create.call_count == 2

        # Check first call
        first_call = executor.worktree_manager.create.call_args_list[0]
        assert first_call[1]["task_id"].endswith("/agent-0")
        assert "agent-0" in first_call[1]["branch"]

    @pytest.mark.asyncio
    async def test_collect_results_extracts_diff(self):
        """Should extract diff and files from worktrees."""
        config = FusionConfig(
            prompt="Test task",
            verify="true",
            agent_count=1,
        )

        executor = FusionExecutor(config)

        # Setup initial agent output
        result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Done",
            tools_used=[],
            duration_seconds=1.0,
            model="sonnet",
        )

        executor.agent_outputs["agent-0"] = AgentOutput(
            agent_id="agent-0",
            worktree_branch="fuse/test/agent-0",
            result=result,
            diff="",
            files_changed=[],
            summary="Done",
        )

        # Mock git commands
        executor.worktree_manager._run_git = AsyncMock(
            side_effect=[
                (0, "diff content", ""),  # diff command
                (0, "file1.py\nfile2.py", ""),  # stat command
            ]
        )

        worktree_paths = {"agent-0": "/tmp/worktree"}
        await executor._collect_results(worktree_paths)

        # Verify diff and files were collected
        assert executor.agent_outputs["agent-0"].diff == "diff content"
        assert executor.agent_outputs["agent-0"].files_changed == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_execute_all_agents_fail(self):
        """Should handle case where all agents fail."""
        config = FusionConfig(
            prompt="Impossible task",
            verify="false",  # Will always fail
            agent_count=2,
        )

        executor = FusionExecutor(config)

        # Mock worktree operations
        executor.worktree_manager.create = AsyncMock(return_value="/tmp/worktree")
        executor.worktree_manager.cleanup = AsyncMock()
        executor.worktree_manager._run_git = AsyncMock(return_value=(0, "", ""))

        # Mock grind to return failed results
        failed_result = GrindResult(
            status=GrindStatus.ERROR,
            iterations=1,
            message="Failed",
            tools_used=[],
            duration_seconds=1.0,
            model="sonnet",
        )

        with patch("grind.fusion.grind", AsyncMock(return_value=failed_result)):
            result = await executor.execute(verbose=False)

        assert result.status == "no_viable"
        assert result.decision is None
        assert len(result.agent_outputs) == 2

    @pytest.mark.asyncio
    async def test_execute_some_agents_succeed(self):
        """Should run fusion when at least one agent succeeds."""
        config = FusionConfig(
            prompt="Test task",
            verify="true",
            agent_count=2,
        )

        executor = FusionExecutor(config)

        # Mock worktree operations
        executor.worktree_manager.create = AsyncMock(return_value="/tmp/worktree")
        executor.worktree_manager.cleanup = AsyncMock()
        executor.worktree_manager._run_git = AsyncMock(return_value=(0, "diff", ""))

        # Mock grind to return one success and one failure
        success_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="Success",
            tools_used=["Edit"],
            duration_seconds=5.0,
            model="sonnet",
        )

        failed_result = GrindResult(
            status=GrindStatus.ERROR,
            iterations=1,
            message="Failed",
            tools_used=[],
            duration_seconds=1.0,
            model="sonnet",
        )

        # Create fusion response
        fusion_response = json.dumps({
            "decision": "best-pick",
            "selected_agents": ["agent-0"],
            "reasoning": "Agent 0 succeeded while agent 1 failed.",
            "confidence": 0.95,
            "hybrid_instructions": None,
        })

        fusion_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message=fusion_response,
            tools_used=[],
            duration_seconds=2.0,
            model="opus",
        )

        # Mock grind to return different results for each call
        call_count = 0

        async def mock_grind(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First two calls are agents
                return success_result if call_count == 1 else failed_result
            else:  # Third call is fusion
                return fusion_result

        with patch("grind.fusion.grind", side_effect=mock_grind):
            result = await executor.execute(verbose=False)

        assert result.status == "success"
        assert result.decision is not None
        assert result.decision.strategy_used == "best-pick"
        assert len(result.agent_outputs) == 2


# ============================================================================
# Integration Test
# ============================================================================


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fusion_end_to_end_simple():
    """End-to-end integration test with trivial task."""
    import tempfile
    import os
    from pathlib import Path

    # Create a temporary directory for the test
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        os.chdir(test_dir)

        # Initialize a git repo
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'test@example.com' > /dev/null 2>&1")
        os.system("git config user.name 'Test User' > /dev/null 2>&1")

        # Create initial commit
        (test_dir / "README.md").write_text("# Test\n")
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'Initial commit' > /dev/null 2>&1")

        # Configure fusion to create a simple file
        config = FusionConfig(
            prompt="Create a file named output.txt with the content 'Hello from fusion'",
            verify="test -f output.txt && grep -q 'Hello from fusion' output.txt",
            agent_count=2,
            strategy="best-pick",
            model="haiku",
            fusion_model="sonnet",
            max_iterations=3,
        )

        executor = FusionExecutor(config)

        # Run fusion
        result = await executor.execute(verbose=True)

        # Verify results
        assert result.session_id.startswith("fuse_")
        assert len(result.agent_outputs) == 2

        # At least one agent should succeed
        successful_agents = [
            output for output in result.agent_outputs.values()
            if output.result and output.result.status == GrindStatus.COMPLETE
        ]
        assert len(successful_agents) > 0, "At least one agent should succeed"

        # If any agent succeeded, fusion should have been attempted
        if successful_agents:
            # Fusion might succeed or fail, but it should have been attempted
            # and a decision made (or decision is None if fusion failed)
            assert result.status in ("success", "fusion_failed")
