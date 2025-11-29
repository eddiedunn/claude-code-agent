"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_sdk_client():
    """Mock ClaudeSDKClient for testing grind loop."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.query = AsyncMock()
    return client


@pytest.fixture
def make_assistant_message():
    """Factory for creating mock AssistantMessage objects."""
    def _make(text: str, tools: list[str] = None):
        msg = MagicMock()
        blocks = []
        if text:
            text_block = MagicMock()
            text_block.text = text
            blocks.append(text_block)
        for tool in (tools or []):
            tool_block = MagicMock()
            tool_block.name = tool
            blocks.append(tool_block)
        msg.content = blocks
        return msg
    return _make


@pytest.fixture
def make_result_message():
    """Factory for creating mock ResultMessage objects."""
    def _make():
        return MagicMock()
    return _make


@pytest.fixture
def temp_task_file(tmp_path):
    """Create a temporary task file."""
    task_file = tmp_path / "test_tasks.yaml"
    content = """
tasks:
  - task: "Test task"
    verify: "echo test"
    model: haiku
    max_iterations: 3
"""
    task_file.write_text(content)
    return task_file


@pytest.fixture
def sample_task_definition():
    """Sample task definition for testing."""
    from grind.models import TaskDefinition
    return TaskDefinition(
        task="Fix tests",
        verify="pytest",
        model="sonnet",
        max_iterations=5
    )


@pytest.fixture
def sample_grind_result():
    """Sample grind result for testing."""
    from grind.models import GrindResult, GrindStatus
    return GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=3,
        message="All tests passed",
        tools_used=["Read", "Write", "Bash"],
        duration_seconds=45.2,
        hooks_executed=[],
        model="sonnet"
    )
