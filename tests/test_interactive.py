"""Tests for grind.interactive module."""

import pytest
from unittest.mock import patch, MagicMock
from grind.interactive import (
    get_checkpoint_input,
    InterjectState,
    start_keyboard_listener,
    stop_keyboard_listener,
    is_interject_requested,
    clear_interject,
)
from grind.models import CheckpointAction


class TestInterjectState:
    """Test InterjectState class."""

    def test_request_interject(self):
        state = InterjectState()
        assert state.requested is False
        state.request_interject()
        assert state.requested is True

    def test_clear_interject(self):
        state = InterjectState()
        state.request_interject()
        assert state.requested is True
        state.clear_interject()
        assert state.requested is False

    def test_is_interject_requested(self):
        state = InterjectState()
        assert state.is_interject_requested() is False
        state.request_interject()
        assert state.is_interject_requested() is True


class TestCheckpointInput:
    """Test get_checkpoint_input function."""

    @patch('builtins.input', return_value='')
    @patch('sys.stdin.isatty', return_value=False)
    def test_empty_input_continues(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.CONTINUE
        assert guidance is None

    @patch('builtins.input', return_value='a')
    @patch('sys.stdin.isatty', return_value=False)
    def test_abort_action(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.ABORT
        assert guidance is None

    @patch('builtins.input', return_value='s')
    @patch('sys.stdin.isatty', return_value=False)
    def test_status_action(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.STATUS
        assert guidance is None

    @patch('builtins.input', return_value='v')
    @patch('sys.stdin.isatty', return_value=False)
    def test_verify_action(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.RUN_VERIFY
        assert guidance is None

    @patch('builtins.input', side_effect=['g', 'test guidance'])
    @patch('sys.stdin.isatty', return_value=False)
    def test_guidance_action(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.GUIDANCE
        assert guidance == 'test guidance'

    @patch('builtins.input', side_effect=['p', 'persistent guidance'])
    @patch('sys.stdin.isatty', return_value=False)
    def test_persistent_guidance_action(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.GUIDANCE_PERSIST
        assert guidance == 'persistent guidance'

    @patch('builtins.input', return_value='custom input')
    @patch('sys.stdin.isatty', return_value=False)
    def test_unknown_input_becomes_guidance(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.GUIDANCE
        assert guidance == 'custom input'

    @patch('builtins.input', side_effect=EOFError)
    @patch('sys.stdin.isatty', return_value=False)
    def test_eof_error_continues(self, mock_isatty, mock_input):
        action, guidance = get_checkpoint_input()
        assert action == CheckpointAction.CONTINUE
        assert guidance is None


class TestKeyboardListener:
    """Test keyboard listener functions."""

    @patch('sys.stdin.isatty', return_value=False)
    def test_start_listener_no_tty(self, mock_isatty):
        """Should not start listener when not a TTY."""
        start_keyboard_listener()
        # Should return early without error

    @patch('sys.stdin.isatty', return_value=False)
    def test_interject_requested(self, mock_isatty):
        """Test checking interject request."""
        clear_interject()
        assert is_interject_requested() is False
