"""Tests for FooterShell widget."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from grind.tui.core.shell_commands import CommandRegistry, ShellContext
from grind.tui.widgets.footer_shell import FooterShell
from grind.tui.core.session import AgentSession


class TestApp(App):
    """Test app to mount widgets."""

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self) -> ComposeResult:
        yield self.widget


@pytest.fixture
def command_registry():
    """Create a command registry."""
    return CommandRegistry()


@pytest.fixture
def shell_context():
    """Create a shell context."""
    session = AgentSession()
    return ShellContext(
        session=session,
        agents=[],
        current_agent_id=None,
        history=[],
        variables={},
    )


@pytest.fixture
def footer_shell(command_registry, shell_context):
    """Create a footer shell instance."""
    shell = FooterShell(
        command_registry=command_registry,
        shell_context=shell_context,
    )
    return shell


def test_footer_shell_initialization(footer_shell, command_registry):
    """Test footer shell initializes correctly."""
    assert footer_shell.history == []
    assert footer_shell.history_index == -1
    assert footer_shell._output_lines == []
    assert footer_shell.command_registry == command_registry


def test_footer_shell_history_append(footer_shell):
    """Test command history is recorded."""
    footer_shell.history.append("help")
    footer_shell.history.append("agents")
    assert footer_shell.history == ["help", "agents"]
    assert len(footer_shell.history) == 2


def test_footer_shell_get_completions_empty(footer_shell):
    """Test completions with empty input."""
    completions = footer_shell.get_completions("")
    assert completions == []


def test_footer_shell_css_valid(footer_shell):
    """Test footer shell CSS is valid."""
    css = footer_shell.DEFAULT_CSS

    # Should have proper Textual CSS structure
    assert "FooterShell {" in css
    assert "#shell-output" in css or "output" in css.lower()
    assert "#shell-input" in css or "input" in css.lower()
    assert "#shell-prompt" in css or "prompt" in css.lower()


def test_footer_shell_css_collapsed_expanded(footer_shell):
    """Test CSS defines collapsed/expanded states."""
    css = footer_shell.DEFAULT_CSS

    # Should have state-based CSS
    assert ".collapsed" in css
    assert ".expanded" in css


def test_footer_shell_no_context(command_registry):
    """Test footer shell can initialize without context."""
    shell = FooterShell(command_registry=command_registry)
    assert shell.shell_context is None
    assert shell.command_registry == command_registry


def test_footer_shell_no_registry():
    """Test footer shell can initialize without registry."""
    shell = FooterShell()
    assert shell.command_registry is not None  # Should create default
    assert isinstance(shell.command_registry, CommandRegistry)


def test_footer_shell_history_state(footer_shell):
    """Test history index management."""
    assert footer_shell.history_index == -1

    footer_shell.history.append("cmd1")
    footer_shell.history.append("cmd2")

    # Simulate history navigation
    footer_shell.history_index = 0
    assert footer_shell.history[footer_shell.history_index] == "cmd1"

    footer_shell.history_index = 1
    assert footer_shell.history[footer_shell.history_index] == "cmd2"

    # Reset
    footer_shell.history_index = -1
    assert footer_shell.history_index == -1


def test_footer_shell_methods_exist(footer_shell):
    """Test footer shell has required methods."""
    assert hasattr(footer_shell, "expand")
    assert hasattr(footer_shell, "collapse")
    assert hasattr(footer_shell, "toggle")
    assert hasattr(footer_shell, "write_output")
    assert hasattr(footer_shell, "clear_output")
    assert hasattr(footer_shell, "get_completions")
    assert hasattr(footer_shell, "on_input_submitted")


def test_footer_shell_state_attributes(footer_shell):
    """Test footer shell state attributes."""
    # Test all expected attributes exist
    assert hasattr(footer_shell, "history")
    assert hasattr(footer_shell, "history_index")
    assert hasattr(footer_shell, "_output_lines")
    assert hasattr(footer_shell, "command_registry")
    assert hasattr(footer_shell, "shell_context")
