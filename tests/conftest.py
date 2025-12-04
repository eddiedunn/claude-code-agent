"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from grind.logging import disable_logging, enable_logging, reset_logger


@pytest.fixture(autouse=True)
def isolate_logging():
    """Disable file logging during tests to prevent polluting .grind/logs/."""
    disable_logging()
    reset_logger()
    yield
    reset_logger()
    enable_logging()


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


@pytest.fixture
def sample_task_def() -> 'TaskDefinition':
    """Standard TaskDefinition for testing."""
    from grind.models import TaskDefinition
    return TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet"
    )


@pytest.fixture
def dag_graph_linear() -> 'TaskGraph':
    """Linear DAG: A -> B -> C."""
    from grind.models import TaskGraph, TaskNode, TaskDefinition
    graph = TaskGraph()
    graph.nodes["A"] = TaskNode(id="A", task_def=TaskDefinition(task="A", verify="echo A"))
    graph.nodes["B"] = TaskNode(id="B", task_def=TaskDefinition(task="B", verify="echo B"), depends_on=["A"])
    graph.nodes["C"] = TaskNode(id="C", task_def=TaskDefinition(task="C", verify="echo C"), depends_on=["B"])
    return graph


@pytest.fixture
def dag_graph_diamond() -> 'TaskGraph':
    """Diamond DAG: A -> B,C -> D."""
    from grind.models import TaskGraph, TaskNode, TaskDefinition
    graph = TaskGraph()
    graph.nodes["A"] = TaskNode(id="A", task_def=TaskDefinition(task="A", verify="echo A"))
    graph.nodes["B"] = TaskNode(id="B", task_def=TaskDefinition(task="B", verify="echo B"), depends_on=["A"])
    graph.nodes["C"] = TaskNode(id="C", task_def=TaskDefinition(task="C", verify="echo C"), depends_on=["A"])
    graph.nodes["D"] = TaskNode(id="D", task_def=TaskDefinition(task="D", verify="echo D"), depends_on=["B", "C"])
    return graph
