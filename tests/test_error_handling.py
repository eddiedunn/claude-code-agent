"""Tests for error handling logic in grind/engine.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import real SDK classes for spec
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from grind.engine import grind
from grind.models import GrindStatus, TaskDefinition


def create_mock_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock with correct type for isinstance checks."""
    block = MagicMock(spec=TextBlock)
    block.text = text
    block.is_error = False
    return block


def create_mock_assistant_message(blocks: list) -> MagicMock:
    """Create a mock AssistantMessage with correct type for isinstance checks."""
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def create_mock_result_message(is_error: bool = False, duration_ms: int = 1000) -> MagicMock:
    """Create a mock ResultMessage with correct type for isinstance checks."""
    mock = MagicMock(spec=ResultMessage)
    # Set required attributes for logging
    mock.duration_ms = duration_ms
    mock.duration_api_ms = int(duration_ms * 0.8)
    mock.is_error = is_error
    mock.num_turns = 1
    mock.session_id = "test-session-123"
    mock.total_cost_usd = 0.001
    mock.usage = {"input_tokens": 100, "output_tokens": 50}
    return mock


@pytest.mark.asyncio
async def test_consecutive_error_detection(mock_sdk_client):
    """Test that grind exits after 3 consecutive errors with ERROR status."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=10,
        model="sonnet",
    )

    # Track iteration count
    iteration_count = 0

    async def mock_receive():
        """Return 3 consecutive errors."""
        nonlocal iteration_count
        iteration_count += 1

        # Return error messages for first 3 iterations
        text_block = create_mock_text_block("Error occurred")
        assistant_msg = create_mock_assistant_message([text_block])
        result_msg = create_mock_result_message(is_error=True)

        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    # Verify we stopped after 3 iterations
    assert iteration_count == 3, f"Expected 3 iterations, got {iteration_count}"

    # Verify status is ERROR not MAX_ITERATIONS
    assert result.status == GrindStatus.ERROR
    msg_lower = result.message.lower()
    assert "consecutive" in msg_lower and "error" in msg_lower
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_fast_failure_detection(mock_sdk_client):
    """Test that fast failures (< 2 seconds with errors) are detected and cause early exit."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock

    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=10,
        model="sonnet",
    )

    iteration_count = 0
    base_time = datetime(2024, 1, 1, 12, 0, 0)
    time_offset = [0.0]  # Tracks time offset in seconds

    # Create a mock datetime class
    mock_datetime = MagicMock()

    def mock_now():
        """Return current mocked time."""
        return base_time + timedelta(seconds=time_offset[0])

    mock_datetime.now = mock_now

    async def mock_receive():
        """Return fast failures (errors in < 2 seconds)."""
        nonlocal iteration_count
        iteration_count += 1

        # Simulate very fast iteration (0.5 seconds)
        time_offset[0] += 0.5

        # Return error messages
        text_block = create_mock_text_block("Fast error")
        assistant_msg = create_mock_assistant_message([text_block])
        result_msg = create_mock_result_message(is_error=True)

        yield assistant_msg
        yield result_msg

    async def mock_sleep(delay):
        """Mock sleep - advance time but don't actually sleep."""
        # Don't advance time during sleep to ensure iterations stay fast
        pass

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client), \
         patch('grind.engine.datetime', mock_datetime), \
         patch('asyncio.sleep', side_effect=mock_sleep):
        result = await grind(task_def)

    # Verify we stopped after 3 fast failures
    assert iteration_count == 3, f"Expected 3 iterations, got {iteration_count}"

    # Verify status is ERROR
    assert result.status == GrindStatus.ERROR
    msg_lower = result.message.lower()
    assert "fast failure" in msg_lower
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_backoff_timing(mock_sdk_client):
    """Test that backoff delays are applied correctly (1s, 2s, 4s)."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=10,
        model="sonnet",
    )

    sleep_calls = []
    iteration_count = 0

    async def mock_receive():
        """Return errors to trigger backoff."""
        nonlocal iteration_count
        iteration_count += 1

        text_block = create_mock_text_block("Error")
        assistant_msg = create_mock_assistant_message([text_block])
        result_msg = create_mock_result_message(is_error=True)

        yield assistant_msg
        yield result_msg

    async def mock_sleep(delay):
        """Track sleep calls to verify backoff."""
        sleep_calls.append(delay)

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client), \
         patch('grind.engine.asyncio.sleep', side_effect=mock_sleep):
        result = await grind(task_def)

    # Verify backoff delays: 1s (after 1st error), 2s (after 2nd error), 4s (after 3rd error)
    # Note: The backoff is applied before the next iteration, so we should see:
    # - After iteration 1 (1st error): 1s backoff
    # - After iteration 2 (2nd error): 2s backoff
    # - Iteration 3 completes with 3rd error and exits
    assert len(sleep_calls) == 2, f"Expected 2 sleep calls, got {len(sleep_calls)}: {sleep_calls}"
    assert sleep_calls[0] == 1, f"First backoff should be 1s, got {sleep_calls[0]}s"
    assert sleep_calls[1] == 2, f"Second backoff should be 2s, got {sleep_calls[1]}s"

    assert result.status == GrindStatus.ERROR


@pytest.mark.asyncio
async def test_error_recovery(mock_sdk_client):
    """Test that counters reset after success and task completes normally."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=10,
        model="sonnet",
    )

    iteration_count = 0

    async def mock_receive():
        """Return: error, error, success, complete."""
        nonlocal iteration_count
        iteration_count += 1

        # First two iterations: errors
        if iteration_count <= 2:
            text_block = create_mock_text_block("Error")
            assistant_msg = create_mock_assistant_message([text_block])
            result_msg = create_mock_result_message(is_error=True)
        # Third iteration: success (no error)
        elif iteration_count == 3:
            text_block = create_mock_text_block("Fixed the issue")
            assistant_msg = create_mock_assistant_message([text_block])
            result_msg = create_mock_result_message(is_error=False)
        # Fourth iteration: complete signal
        else:
            text_block = create_mock_text_block("GRIND_COMPLETE: All tests pass")
            assistant_msg = create_mock_assistant_message([text_block])
            result_msg = create_mock_result_message(is_error=False)

        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    # Verify task completed successfully after recovery
    assert result.status == GrindStatus.COMPLETE
    assert iteration_count == 4, f"Expected 4 iterations, got {iteration_count}"
    assert "All tests pass" in result.message


@pytest.mark.asyncio
async def test_error_message_accuracy(mock_sdk_client):
    """Test that GrindResult.message contains useful error details."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=10,
        model="sonnet",
    )

    async def mock_receive():
        """Return consecutive errors."""
        text_block = create_mock_text_block("API Error")
        assistant_msg = create_mock_assistant_message([text_block])
        result_msg = create_mock_result_message(is_error=True)

        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        result = await grind(task_def)

    # Verify error message contains useful details
    assert result.status == GrindStatus.ERROR
    assert result.message is not None
    assert len(result.message) > 0

    # Error message should mention consecutive errors and the count
    msg_lower = result.message.lower()
    assert "3" in result.message or "consecutive" in msg_lower
    assert "error" in msg_lower

    # Message should indicate it's stopping to prevent wasted iterations
    assert "stopping" in msg_lower or "prevent" in msg_lower
