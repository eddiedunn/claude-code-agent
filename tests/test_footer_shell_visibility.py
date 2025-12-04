"""Test that FooterShell is actually visible and interactive in the TUI."""

import pytest
from textual.widgets import Input

from grind.tui.app import AgentTUI
from grind.tui.widgets.footer_shell import FooterShell


@pytest.mark.asyncio
async def test_footer_shell_is_visible_in_app():
    """Test that FooterShell is mounted and visible in the app."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        # Wait for app to mount
        await pilot.pause()

        # FooterShell should be mounted
        footer_shell = app.query_one("#footer-shell", FooterShell)
        assert footer_shell is not None

        # Should be in collapsed state initially
        assert footer_shell.has_class("collapsed")
        assert not footer_shell.has_class("expanded")

        # Should not be expanded
        assert footer_shell.expanded is False


@pytest.mark.asyncio
async def test_footer_shell_toggle_with_ctrl_backtick():
    """Test that Ctrl+` toggles the FooterShell."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Initially collapsed
        assert footer_shell.expanded is False
        assert footer_shell.has_class("collapsed")

        # Press Ctrl+` to expand
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Should now be expanded
        assert footer_shell.expanded is True
        assert footer_shell.has_class("expanded")
        assert not footer_shell.has_class("collapsed")

        # Press Ctrl+` again to collapse
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Should be collapsed again
        assert footer_shell.expanded is False
        assert footer_shell.has_class("collapsed")


@pytest.mark.asyncio
async def test_footer_shell_input_is_accessible():
    """Test that the input field in FooterShell is accessible."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Expand the shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Input should exist and be focusable
        shell_input = footer_shell.query_one("#shell-input", Input)
        assert shell_input is not None

        # Input should be focused after expansion
        assert shell_input.has_focus


@pytest.mark.asyncio
async def test_footer_shell_command_submission():
    """Test that commands can be submitted through FooterShell."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Expand shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Type a command
        shell_input = footer_shell.query_one("#shell-input", Input)
        shell_input.value = "help"

        # Submit command
        await pilot.press("enter")
        await pilot.pause()

        # Command should be added to history
        assert "help" in footer_shell.history

        # Input should be cleared
        assert shell_input.value == ""


@pytest.mark.asyncio
async def test_footer_shell_history_navigation():
    """Test that history can be navigated with up/down arrows."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Expand shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Submit two commands
        shell_input = footer_shell.query_one("#shell-input", Input)

        shell_input.value = "command1"
        await pilot.press("enter")
        await pilot.pause()

        shell_input.value = "command2"
        await pilot.press("enter")
        await pilot.pause()

        # Navigate history with up arrow
        await pilot.press("up")
        await pilot.pause()

        # Should show last command
        assert shell_input.value == "command2"

        # Press up again
        await pilot.press("up")
        await pilot.pause()

        # Should show first command
        assert shell_input.value == "command1"

        # Press down
        await pilot.press("down")
        await pilot.pause()

        # Should show command2 again
        assert shell_input.value == "command2"


@pytest.mark.asyncio
async def test_footer_shell_escape_to_collapse():
    """Test that Escape key collapses the shell."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Expand shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        assert footer_shell.expanded is True

        # Press Escape to collapse
        await pilot.press("escape")
        await pilot.pause()

        # Should be collapsed
        assert footer_shell.expanded is False
