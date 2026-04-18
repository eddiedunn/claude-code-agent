"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from grind.logging import disable_logging, enable_logging, reset_logger, reset_session


@pytest.fixture(autouse=True)
def isolate_logging():
    """Disable file logging during tests to prevent polluting .grind/logs/."""
    disable_logging()
    reset_logger()
    reset_session()
    yield
    reset_logger()
    reset_session()
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


