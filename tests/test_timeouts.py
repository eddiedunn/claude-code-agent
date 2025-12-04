"""Tests for timeout handling in grind engine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from grind.engine import grind
from grind.models import GrindStatus, TaskDefinition


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
    mock = MagicMock(spec=ResultMessage)
    # Set required attributes for logging
    mock.duration_ms = 1000
    mock.duration_api_ms = 800
    mock.is_error = False
    mock.num_turns = 1
    mock.session_id = "test-session-123"
    mock.total_cost_usd = 0.001
    mock.usage = {"input_tokens": 100, "output_tokens": 50}
    return mock


@pytest.mark.asyncio
async def test_query_timeout_initial_request(mock_sdk_client):
    """Test that initial query timeout returns ERROR status."""
    # Create TaskDefinition with query_timeout=1
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
        query_timeout=1,
    )

    # Mock client.query to hang (await asyncio.sleep(10))
    async def hanging_query(*args, **kwargs):
        await asyncio.sleep(10)

    mock_sdk_client.query = AsyncMock(side_effect=hanging_query)

    with patch("grind.engine.ClaudeSDKClient", return_value=mock_sdk_client):
        result = await grind(task_def)

    # Assert it returns ERROR status within timeout
    assert result.status == GrindStatus.ERROR
    # Assert error message mentions timeout
    assert "timed out" in result.message.lower()
    assert result.iterations == 0


@pytest.mark.asyncio
async def test_query_timeout_continue_prompt(mock_sdk_client):
    """Test that continue prompt timeout doesn't crash the grind loop."""
    # Set query_timeout=1
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="sonnet",
        query_timeout=1,
    )

    # Track query calls
    query_calls = []

    # First query succeeds, continue prompts timeout
    async def selective_query(prompt_text: str):
        query_calls.append(prompt_text)
        # Continue prompts timeout
        if "continue" in prompt_text.lower():
            await asyncio.sleep(10)

    mock_sdk_client.query = AsyncMock(side_effect=selective_query)

    # Mock receive_response to never send GRIND_COMPLETE
    iteration_count = [0]

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

    with patch("grind.engine.ClaudeSDKClient", return_value=mock_sdk_client):
        result = await grind(task_def)

    # Assert grind continues gracefully (doesn't crash)
    # Should reach max iterations since no GRIND_COMPLETE signal
    assert result.status == GrindStatus.MAX_ITERATIONS
    assert result.iterations == task_def.max_iterations


@pytest.mark.asyncio
async def test_iteration_timeout_recovery(mock_sdk_client):
    """Test that grind recovers from receive_response timeout and continues."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet",
        query_timeout=1,
    )

    # Track iterations
    iteration_count = [0]
    timeout_triggered = [False]

    # Mock receive_response to timeout once then succeed
    def mock_receive():
        async def _receive():
            iteration_count[0] += 1

            # First iteration: timeout
            if iteration_count[0] == 1:
                timeout_triggered[0] = True
                await asyncio.sleep(10)  # This will cause timeout
            # Second iteration: succeed with completion
            else:
                text_block = create_mock_text_block("GRIND_COMPLETE: Recovered")
                assistant_msg = create_mock_assistant_message([text_block])
                result_msg = create_mock_result_message()
                yield assistant_msg
                yield result_msg

        return _receive()

    mock_sdk_client.receive_response = mock_receive

    with patch("grind.engine.ClaudeSDKClient", return_value=mock_sdk_client):
        result = await grind(task_def)

    # Assert grind recovers and continues to next iteration
    assert timeout_triggered[0], "Timeout should have been triggered"
    assert iteration_count[0] >= 2, "Should have continued after timeout"
    assert result.status == GrindStatus.COMPLETE
    assert result.message == "Recovered"


@pytest.mark.asyncio
async def test_timeout_with_partial_response(mock_sdk_client):
    """Test that partial data is handled when receive_response times out."""
    task_def = TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=3,
        model="sonnet",
        query_timeout=1,
    )

    partial_data_yielded = [False]

    # Mock receive_response to yield partial data then timeout
    def mock_receive():
        async def _receive():
            # Yield some partial data
            text_block = create_mock_text_block("Partial response data...")
            tool_block = create_mock_tool_block("Read", "tool_1")
            assistant_msg = create_mock_assistant_message([text_block, tool_block])
            yield assistant_msg
            partial_data_yielded[0] = True

            # Then timeout (no ResultMessage)
            await asyncio.sleep(10)

        return _receive()

    mock_sdk_client.receive_response = mock_receive

    with patch("grind.engine.ClaudeSDKClient", return_value=mock_sdk_client):
        result = await grind(task_def)

    # Assert partial data was yielded
    assert partial_data_yielded[0], "Partial data should have been yielded"

    # Assert grind continues or fails gracefully
    # Should reach MAX_ITERATIONS since we timeout on each iteration
    assert result.status == GrindStatus.MAX_ITERATIONS
    assert result.iterations == task_def.max_iterations
