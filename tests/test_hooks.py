"""Tests for grind/hooks.py hook execution functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from grind.hooks import execute_slash_command, execute_hooks
from grind.models import SlashCommandHook, HookTrigger

# Import real SDK classes for spec
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


def create_mock_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock with correct type for isinstance checks."""
    block = MagicMock(spec=TextBlock)
    block.text = text
    return block


def create_mock_assistant_message(blocks: list) -> MagicMock:
    """Create a mock AssistantMessage with correct type for isinstance checks."""
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def create_mock_result_message() -> MagicMock:
    """Create a mock ResultMessage with correct type for isinstance checks."""
    return MagicMock(spec=ResultMessage)


@pytest.mark.asyncio
async def test_execute_slash_command_success():
    """Test execute_slash_command with successful command execution."""
    # Create mock client
    client = AsyncMock()
    client.query = AsyncMock()

    # Create response messages
    text_block = create_mock_text_block("Command output")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    # Mock receive_response async generator
    async def mock_receive():
        yield assistant_msg
        yield result_msg

    client.receive_response = mock_receive

    # Execute command
    success, output = await execute_slash_command(client, "/test")

    # Assertions
    assert success is True
    assert output == "Command output"
    client.query.assert_called_once_with("/test")


@pytest.mark.asyncio
async def test_execute_slash_command_failure():
    """Test execute_slash_command with exception handling."""
    # Create mock client that raises exception
    client = AsyncMock()
    client.query = AsyncMock(side_effect=Exception("Failed"))

    # Execute command
    success, output = await execute_slash_command(client, "/test")

    # Assertions
    assert success is False
    assert output == "Failed"


@pytest.mark.asyncio
async def test_execute_hooks_filters_by_should_run():
    """Test execute_hooks filters hooks using should_run method."""
    # Create mock client
    client = AsyncMock()
    client.query = AsyncMock()

    # Create response for successful execution
    text_block = create_mock_text_block("Success")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    client.receive_response = mock_receive

    # Create hooks with different triggers
    hook_once = SlashCommandHook(command="/once", trigger=HookTrigger.ONCE)
    hook_every = SlashCommandHook(command="/every", trigger=HookTrigger.EVERY)
    hook_every_5 = SlashCommandHook(command="/every_5", trigger=HookTrigger.EVERY_N, trigger_count=5)
    hook_every_3 = SlashCommandHook(command="/every_3", trigger=HookTrigger.EVERY_N, trigger_count=3)

    hooks = [hook_once, hook_every, hook_every_5, hook_every_3]

    # Execute hooks at iteration 5 (should run: every, every_5)
    # ONCE hook runs only on iteration 1, so it won't run on iteration 5
    results = await execute_hooks(client, hooks, iteration=5, is_error=False)

    # Extract executed commands
    executed_commands = [cmd for cmd, _, _ in results]

    # At iteration 5:
    # - hook_once: should_run(5, False) = False (only runs at iteration 1)
    # - hook_every: should_run(5, False) = True (runs every iteration)
    # - hook_every_5: should_run(5, False) = True (5 % 5 == 0)
    # - hook_every_3: should_run(5, False) = False (5 % 3 != 0)
    assert "/every" in executed_commands
    assert "/every_5" in executed_commands
    assert "/once" not in executed_commands
    assert "/every_3" not in executed_commands


@pytest.mark.asyncio
async def test_execute_hooks_passes_error_flag():
    """Test execute_hooks passes is_error flag to should_run method."""
    # Create mock client
    client = AsyncMock()
    client.query = AsyncMock()

    # Create response for successful execution
    text_block = create_mock_text_block("Error handled")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    client.receive_response = mock_receive

    # Create ON_ERROR hook
    hook_on_error = SlashCommandHook(command="/on_error", trigger=HookTrigger.ON_ERROR)
    hooks = [hook_on_error]

    # Execute with is_error=True
    results_with_error = await execute_hooks(client, hooks, iteration=1, is_error=True)
    executed_with_error = [cmd for cmd, _, _ in results_with_error]

    # Execute with is_error=False
    results_without_error = await execute_hooks(client, hooks, iteration=1, is_error=False)
    executed_without_error = [cmd for cmd, _, _ in results_without_error]

    # Assertions
    assert "/on_error" in executed_with_error
    assert "/on_error" not in executed_without_error


@pytest.mark.asyncio
async def test_execute_hooks_returns_all_results():
    """Test execute_hooks returns list of all results as tuples."""
    # Create mock client
    client = AsyncMock()
    client.query = AsyncMock()

    # Create response for successful execution
    text_block = create_mock_text_block("Output")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    call_count = 0
    async def mock_receive():
        nonlocal call_count
        call_count += 1
        yield assistant_msg
        yield result_msg

    client.receive_response = mock_receive

    # Create 3 hooks that all should run
    hook1 = SlashCommandHook(command="/cmd1", trigger=HookTrigger.EVERY)
    hook2 = SlashCommandHook(command="/cmd2", trigger=HookTrigger.EVERY)
    hook3 = SlashCommandHook(command="/cmd3", trigger=HookTrigger.EVERY)

    hooks = [hook1, hook2, hook3]

    # Execute hooks
    results = await execute_hooks(client, hooks, iteration=1, is_error=False)

    # Assertions
    assert len(results) == 3

    # Verify each result is a tuple of (command, output, success)
    for result in results:
        assert isinstance(result, tuple)
        assert len(result) == 3
        command, output, success = result
        assert command in ["/cmd1", "/cmd2", "/cmd3"]
        assert output == "Output"
        assert success is True


@pytest.mark.asyncio
async def test_execute_hooks_empty_list():
    """Test execute_hooks with empty hooks list."""
    # Create mock client
    client = AsyncMock()

    # Execute with empty hooks list
    results = await execute_hooks(client, [], iteration=1, is_error=False)

    # Assertions
    assert results == []
    assert isinstance(results, list)
