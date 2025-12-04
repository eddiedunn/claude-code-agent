"""Tests for grind/engine.py decompose() function."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import real SDK classes for spec
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from grind.engine import decompose
from grind.models import TaskDefinition


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


@pytest.fixture
def mock_sdk_client():
    """Mock ClaudeSDKClient for testing decompose."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.query = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_decompose_basic_response(mock_sdk_client):
    """Test decompose with a basic JSON response containing tasks."""
    # Create a response with JSON containing tasks
    json_response = {
        "tasks": [
            {
                "task": "Install dependencies",
                "verify": "npm install",
                "max_iterations": 3,
            },
            {
                "task": "Run tests",
                "verify": "npm test",
                "max_iterations": 5,
            }
        ]
    }
    text_block = create_mock_text_block(f"Here are the tasks:\n{json.dumps(json_response)}")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        tasks = await decompose("Fix the build", "npm run build")

    assert len(tasks) == 2
    assert tasks[0].task == "Install dependencies"
    assert tasks[0].verify == "npm install"
    assert tasks[0].max_iterations == 3
    assert tasks[1].task == "Run tests"
    assert tasks[1].verify == "npm test"
    assert tasks[1].max_iterations == 5


@pytest.mark.asyncio
async def test_decompose_model_selection(mock_sdk_client):
    """Test that decompose respects model field in task definitions."""
    json_response = {
        "tasks": [
            {
                "task": "Simple task",
                "verify": "echo test",
                "model": "haiku",
            },
            {
                "task": "Complex task",
                "verify": "pytest",
                "model": "opus",
            }
        ]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        tasks = await decompose("Test problem", "pytest")

    assert len(tasks) == 2
    assert tasks[0].model == "haiku"
    assert tasks[1].model == "opus"


@pytest.mark.asyncio
async def test_decompose_router_fallback(mock_sdk_client):
    """Test that decompose uses router when model is not specified."""
    json_response = {
        "tasks": [
            {
                "task": "Some task without model",
                "verify": "echo test",
            }
        ]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        tasks = await decompose("Test problem", "pytest")

    assert len(tasks) == 1
    # Should have a model assigned by router (default behavior)
    assert tasks[0].model is not None
    assert isinstance(tasks[0].model, str)


@pytest.mark.asyncio
async def test_decompose_depends_on(mock_sdk_client):
    """Test that decompose correctly parses depends_on field."""
    json_response = {
        "tasks": [
            {
                "task": "Task A",
                "verify": "echo A",
                "depends_on": [],
            },
            {
                "task": "Task B",
                "verify": "echo B",
                "depends_on": ["Task A"],
            },
            {
                "task": "Task C",
                "verify": "echo C",
                "depends_on": ["Task A", "Task B"],
            }
        ]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        tasks = await decompose("Multi-step problem", "echo done")

    assert len(tasks) == 3
    assert tasks[0].depends_on == []
    assert tasks[1].depends_on == ["Task A"]
    assert tasks[2].depends_on == ["Task A", "Task B"]


@pytest.mark.asyncio
async def test_decompose_uses_opus_model(mock_sdk_client):
    """Test that decompose uses opus model for decomposition."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Test problem", "pytest")

        # Check that ClaudeSDKClient was called with opus model
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        assert options.model == "opus"


@pytest.mark.asyncio
async def test_decompose_extended_thinking_params(mock_sdk_client):
    """Test that decompose uses max_thinking_tokens for extended thinking."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Complex problem", "pytest")

        # Check that max_thinking_tokens is set
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        assert options.max_thinking_tokens == 10000


@pytest.mark.asyncio
async def test_decompose_tool_availability(mock_sdk_client):
    """Test that decompose has access to appropriate tools."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Test problem", "pytest")

        # Check that allowed_tools includes necessary tools
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        expected_tools = ["Bash", "Read", "Glob", "Grep", "WebSearch", "WebFetch"]
        assert options.allowed_tools == expected_tools


@pytest.mark.asyncio
async def test_decompose_permission_mode(mock_sdk_client):
    """Test that decompose uses acceptEdits permission mode."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Test problem", "pytest")

        # Check permission mode
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        assert options.permission_mode == "acceptEdits"


@pytest.mark.asyncio
async def test_decompose_cwd_parameter(mock_sdk_client):
    """Test that decompose passes cwd parameter to SDK client."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Test problem", "pytest", cwd="/custom/path")

        # Check cwd
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        assert options.cwd == "/custom/path"


@pytest.mark.asyncio
async def test_decompose_no_json_found(mock_sdk_client):
    """Test that decompose raises ValueError when no JSON is found."""
    # Response without JSON
    text_block = create_mock_text_block("No JSON here, just plain text")
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        with pytest.raises(ValueError, match="No JSON found in response"):
            await decompose("Test problem", "pytest")


@pytest.mark.asyncio
async def test_decompose_max_turns(mock_sdk_client):
    """Test that decompose sets max_turns to 10."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient') as mock_client_cls:
        mock_client_cls.return_value = mock_sdk_client
        await decompose("Test problem", "pytest")

        # Check max_turns
        call_args = mock_client_cls.call_args
        assert call_args is not None
        options = call_args[1]['options']
        assert options.max_turns == 10


@pytest.mark.asyncio
async def test_decompose_default_max_iterations(mock_sdk_client):
    """Test that decompose uses default max_iterations of 5 when not specified."""
    json_response = {
        "tasks": [
            {
                "task": "Task without max_iterations",
                "verify": "echo test",
            }
        ]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        tasks = await decompose("Test problem", "pytest")

    assert len(tasks) == 1
    assert tasks[0].max_iterations == 5


@pytest.mark.asyncio
async def test_decompose_verbose_mode(mock_sdk_client):
    """Test that decompose prints output in verbose mode."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_content = "Decomposing the problem...\n" + json.dumps(json_response)
    text_block = create_mock_text_block(text_content)
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        with patch('builtins.print') as mock_print:
            tasks = await decompose("Test problem", "pytest", verbose=True)

            # Verify print was called (verbose mode should print)
            assert mock_print.called


@pytest.mark.asyncio
async def test_decompose_prompt_formatting(mock_sdk_client):
    """Test that decompose formats the prompt with problem and verify_cmd."""
    json_response = {
        "tasks": [{"task": "Test", "verify": "echo test"}]
    }
    text_block = create_mock_text_block(json.dumps(json_response))
    assistant_msg = create_mock_assistant_message([text_block])
    result_msg = create_mock_result_message()

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_sdk_client.receive_response = mock_receive

    problem = "Fix the failing tests"
    verify_cmd = "pytest tests/"

    with patch('grind.engine.ClaudeSDKClient', return_value=mock_sdk_client):
        await decompose(problem, verify_cmd)

        # Check that query was called
        assert mock_sdk_client.query.called
        call_args = mock_sdk_client.query.call_args[0][0]

        # Verify problem and verify_cmd are in the prompt
        assert problem in call_args
        assert verify_cmd in call_args
