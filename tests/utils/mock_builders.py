"""Mock builders for testing with Claude SDK types."""

from typing import Any, Optional
from unittest.mock import MagicMock

# Import real SDK classes for spec
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


def create_mock_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock with correct type for isinstance checks.

    Args:
        text: The text content for the mock block.

    Returns:
        A MagicMock instance with TextBlock spec and text attribute set.
    """
    block = MagicMock(spec=TextBlock)
    block.text = text
    return block


def create_mock_tool_block(
    name: str, tool_id: str = "tool_1", tool_input: Optional[dict] = None
) -> MagicMock:
    """Create a mock ToolUseBlock with correct type for isinstance checks.

    Args:
        name: The name of the tool.
        tool_id: The unique identifier for the tool. Defaults to "tool_1".
        tool_input: The input dictionary for the tool. Defaults to empty dict.

    Returns:
        A MagicMock instance with ToolUseBlock spec and appropriate attributes.
    """
    block = MagicMock(spec=ToolUseBlock)
    block.name = name
    block.id = tool_id
    block.input = tool_input or {}
    return block


def create_mock_assistant_message(blocks: list[Any]) -> MagicMock:
    """Create a mock AssistantMessage with correct type for isinstance checks.

    Args:
        blocks: A list of content blocks (typically text or tool use blocks).

    Returns:
        A MagicMock instance with AssistantMessage spec and content set to blocks.
    """
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def create_mock_result_message() -> MagicMock:
    """Create a mock ResultMessage with correct type for isinstance checks.

    Returns:
        A MagicMock instance with ResultMessage spec.
    """
    return MagicMock(spec=ResultMessage)


async def mock_receive_response_generator(messages: list[Any]):
    """Create an async generator for receive_response().

    Yields each message in sequence, simulating the SDK's receive_response behavior.

    Args:
        messages: A list of messages to yield.

    Yields:
        Each message in the input list.
    """
    for msg in messages:
        yield msg
