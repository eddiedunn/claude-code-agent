"""Tests for grind/engine.py grind() function."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import real SDK classes for spec
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from grind.engine import grind
from grind.models import GrindHooks, GrindStatus, TaskDefinition


@pytest.fixture
def basic_task_def():
    """Create a basic TaskDefinition for testing."""
    return TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )


def create_mock_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock with correct type for isinstance checks."""
    block = MagicMock(spec=TextBlock)
    block.text = text
    return block


def create_mock_tool_block(
    name: str, tool_id: str = "tool_1", tool_input: dict = None
) -> MagicMock:
    """Create a mock ToolUseBlock with correct type for isinstance checks."""
    block = MagicMock(spec=ToolUseBlock)
    block.name = name
    block.id = tool_id
    block.input = tool_input or {}
    return block


def create_mock_assistant_message(blocks: list) -> MagicMock:
    """Create a mock AssistantMessage with correct type for isinstance checks."""
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def create_mock_result_message() -> MagicMock:
    """Create a mock ResultMessage with correct type for isinstance checks."""
    return MagicMock(spec=ResultMessage)


async def mock_receive_response_generator(messages: list):
    """Create an async generator for receive_response()."""
    for msg in messages:
        yield msg


@pytest.mark.asyncio
async def test_grind_completes_on_success_signal(mock_sdk_client):
    """Test that grind returns COMPLETE status when GRIND_COMPLETE signal is found."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Create messages sequence
    text_block = create_mock_text_block("GRIND_COMPLETE: All tests pass")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert "All tests pass" in result.message


@pytest.mark.asyncio
async def test_grind_stuck_on_stuck_signal(mock_sdk_client):
    """Test that grind returns STUCK status when GRIND_STUCK signal is found."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Create messages sequence
    text_block = create_mock_text_block("GRIND_STUCK: Cannot resolve issue")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.STUCK
    assert "Cannot resolve issue" in result.message


@pytest.mark.asyncio
async def test_grind_max_iterations_reached(mock_sdk_client):
    """Test that grind returns MAX_ITERATIONS when max_iterations is reached."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="sonnet",
    )

    # Track iteration count
    iteration_count = [0]

    # Create messages without completion signal
    def mock_receive():
        async def _receive():
            iteration_count[0] += 1
            text_block = create_mock_text_block("Working on it...")
            assistant_msg = create_mock_assistant_message([text_block])
            result_msg = create_mock_result_message()
            yield assistant_msg
            yield result_msg
        return _receive()

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.MAX_ITERATIONS
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_grind_error_on_exception(mock_sdk_client):
    """Test that grind returns ERROR status when SDK raises an exception."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Make the context manager raise an error
    mock_sdk_client.__aenter__ = AsyncMock(side_effect=Exception("SDK Error"))

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.ERROR
    assert "SDK Error" in result.message


@pytest.mark.asyncio
async def test_grind_tracks_tools_used(mock_sdk_client):
    """Test that grind tracks tools used across iterations."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Create messages with tool use then completion
    text_block = create_mock_text_block("GRIND_COMPLETE: Done")
    tool_block_read = create_mock_tool_block("Read", "tool_1")
    tool_block_write = create_mock_tool_block("Write", "tool_2")
    tool_block_bash = create_mock_tool_block("Bash", "tool_3")

    assistant_msg = create_mock_assistant_message([
        tool_block_read,
        tool_block_write,
        tool_block_bash,
        text_block
    ])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert "Read" in result.tools_used
    assert "Write" in result.tools_used
    assert "Bash" in result.tools_used


@pytest.mark.asyncio
async def test_grind_executes_pre_grind_hooks(mock_sdk_client):
    """Test that grind executes pre_grind hooks before main loop."""
    hooks = GrindHooks(
        pre_grind=["/test-hook"],
        post_iteration=[],
        post_grind=[],
    )
    hooks.normalize()

    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
        hooks=hooks,
    )

    # Create messages sequence for completion
    text_block = create_mock_text_block("GRIND_COMPLETE: Done")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    call_order = []

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    # Track when execute_hooks is called
    async def mock_execute_hooks(client, hooks_list, iteration, is_error, verbose):
        call_order.append(("hooks", hooks_list, iteration))
        return [("/test-hook", "pre_grind", True)]

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client), \
         patch('grind.engine.execute_hooks', side_effect=mock_execute_hooks):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    # Verify hooks were called (iteration 0 for pre_grind)
    assert len(call_order) > 0
    assert call_order[0][2] == 0  # pre_grind hooks are called at iteration 0


@pytest.mark.asyncio
async def test_grind_signal_at_line_start(mock_sdk_client):
    """Test that signal at start of text is detected."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Signal at very start of text
    text_block = create_mock_text_block("GRIND_COMPLETE: Task finished successfully")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert result.message == "Task finished successfully"


@pytest.mark.asyncio
async def test_grind_signal_after_newline(mock_sdk_client):
    """Test that signal after newline is detected."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Signal after newline
    text_block = create_mock_text_block("Working on the task...\nGRIND_COMPLETE: All done")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert result.message == "All done"


@pytest.mark.asyncio
async def test_grind_ignores_signal_in_quoted_text(mock_sdk_client):
    """Test that signal mentioned in quotes does NOT trigger completion."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="sonnet",
    )

    # Signal mentioned in a sentence (false positive case)
    text_block = create_mock_text_block('The GRIND_COMPLETE signal is used to indicate completion.')
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    iteration_count = [0]

    def mock_receive():
        async def _receive():
            iteration_count[0] += 1
            yield assistant_msg
            yield result_msg
        return _receive()

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    # Should NOT complete, should reach max iterations
    assert result.status == GrindStatus.MAX_ITERATIONS
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_grind_signal_without_message(mock_sdk_client):
    """Test that signal without message uses default message."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Signal without colon and message
    text_block = create_mock_text_block("GRIND_COMPLETE")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert result.message == "Task completed"


@pytest.mark.asyncio
async def test_grind_stuck_signal_without_reason(mock_sdk_client):
    """Test that GRIND_STUCK without reason uses default reason."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Signal without colon and reason
    text_block = create_mock_text_block("GRIND_STUCK")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.STUCK
    assert result.message == "Unknown reason"


@pytest.mark.asyncio
async def test_grind_signal_with_multiline_message(mock_sdk_client):
    """Test that only first line of message is captured."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
    )

    # Signal with multiline message
    text_block = create_mock_text_block("GRIND_COMPLETE: First line\nSecond line\nThird line")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    assert result.status == GrindStatus.COMPLETE
    assert result.message == "First line"


@pytest.mark.asyncio
async def test_grind_ignores_signal_mid_sentence(mock_sdk_client):
    """Test that signal in middle of sentence does NOT trigger completion."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="sonnet",
    )

    # Signal in the middle of a sentence (should not match)
    text_block = create_mock_text_block("Done! GRIND_COMPLETE: Success")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    iteration_count = [0]

    def mock_receive():
        async def _receive():
            iteration_count[0] += 1
            yield assistant_msg
            yield result_msg
        return _receive()

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    # Should NOT complete, should reach max iterations
    assert result.status == GrindStatus.MAX_ITERATIONS
    assert result.iterations == 3
