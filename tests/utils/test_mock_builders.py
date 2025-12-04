"""Tests for mock_builders utilities."""

import pytest

from tests.utils.mock_builders import (
    create_mock_assistant_message,
    create_mock_result_message,
    create_mock_text_block,
    create_mock_tool_block,
    mock_receive_response_generator,
)


def test_create_mock_text_block():
    """Test creating a mock text block."""
    text = "Test text content"
    block = create_mock_text_block(text)

    assert isinstance(block, type(block))  # MagicMock instance
    assert block.text == text
    # Verify it has the TextBlock spec
    assert hasattr(block, "text")


def test_create_mock_tool_block():
    """Test creating a mock tool block with default parameters."""
    name = "Read"
    block = create_mock_tool_block(name)

    assert block.name == name
    assert block.id == "tool_1"
    assert block.input == {}


def test_create_mock_tool_block_custom_params():
    """Test creating a mock tool block with custom parameters."""
    name = "Write"
    tool_id = "my_tool"
    tool_input = {"path": "/test/file.txt", "content": "test"}
    block = create_mock_tool_block(name, tool_id=tool_id, tool_input=tool_input)

    assert block.name == name
    assert block.id == tool_id
    assert block.input == tool_input


def test_create_mock_assistant_message():
    """Test creating a mock assistant message."""
    text_block = create_mock_text_block("Test response")
    blocks = [text_block]
    msg = create_mock_assistant_message(blocks)

    assert msg.content == blocks
    assert len(msg.content) == 1
    assert msg.content[0].text == "Test response"


def test_create_mock_assistant_message_multiple_blocks():
    """Test creating a mock assistant message with multiple blocks."""
    text_block = create_mock_text_block("Response text")
    tool_block = create_mock_tool_block("Bash", "tool_1")
    blocks = [tool_block, text_block]
    msg = create_mock_assistant_message(blocks)

    assert len(msg.content) == 2
    assert msg.content[0].name == "Bash"
    assert msg.content[1].text == "Response text"


def test_create_mock_result_message():
    """Test creating a mock result message."""
    msg = create_mock_result_message()
    assert msg is not None


@pytest.mark.asyncio
async def test_mock_receive_response_generator():
    """Test the mock receive response generator."""
    text_block = create_mock_text_block("Test text")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    messages = [assistant_msg, result_msg]
    gen = mock_receive_response_generator(messages)

    # Collect all yielded messages
    received_messages = []
    async for msg in gen:
        received_messages.append(msg)

    assert len(received_messages) == 2
    assert received_messages[0] == assistant_msg
    assert received_messages[1] == result_msg
