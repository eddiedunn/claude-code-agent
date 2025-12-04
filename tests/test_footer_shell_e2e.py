"""End-to-end tests for FooterShell in real TUI context."""

import pytest

from grind.tui.app import AgentTUI
from grind.tui.widgets.footer_shell import FooterShell


@pytest.mark.asyncio
async def test_footer_shell_e2e_complete_workflow():
    """Test complete workflow: expand, type command, submit, navigate history, collapse."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Step 1: Verify initial state (collapsed)
        assert footer_shell.expanded is False
        assert footer_shell.has_class("collapsed")

        # Step 2: Expand with Ctrl+`
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        assert footer_shell.expanded is True
        assert footer_shell.has_class("expanded")

        # Step 3: Type and submit a command
        shell_input = footer_shell.query_one("#shell-input")
        shell_input.value = "help"
        await pilot.press("enter")
        await pilot.pause()

        # Verify command was added to history
        assert "help" in footer_shell.history
        assert shell_input.value == ""  # Input cleared

        # Step 4: Submit another command
        shell_input.value = "clear"
        await pilot.press("enter")
        await pilot.pause()

        assert "clear" in footer_shell.history
        assert len(footer_shell.history) == 2

        # Step 5: Navigate history with up arrow
        await pilot.press("up")
        await pilot.pause()
        assert shell_input.value == "clear"

        await pilot.press("up")
        await pilot.pause()
        assert shell_input.value == "help"

        # Step 6: Navigate down
        await pilot.press("down")
        await pilot.pause()
        assert shell_input.value == "clear"

        # Step 7: Clear input and collapse
        shell_input.value = ""
        await pilot.press("escape")
        await pilot.pause()
        assert footer_shell.expanded is False
        assert footer_shell.has_class("collapsed")


@pytest.mark.asyncio
async def test_footer_shell_visible_from_all_tabs():
    """Test that FooterShell is accessible from all tabs."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Test from DAG tab (default)
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        assert footer_shell.expanded is True

        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        assert footer_shell.expanded is False

        # Switch to Running tab
        await pilot.press("ctrl+2")
        await pilot.pause()

        # Test shell from Running tab (toggle twice to test)
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        first_state = footer_shell.expanded

        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        second_state = footer_shell.expanded

        # Should toggle between states
        assert first_state != second_state

        # Switch to Logs tab
        await pilot.press("ctrl+4")
        await pilot.pause()

        # Test shell from Logs tab (toggle should work)
        initial = footer_shell.expanded
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()
        assert footer_shell.expanded != initial


@pytest.mark.asyncio
async def test_footer_shell_output_area_shows_when_expanded():
    """Test that output area is visible when expanded."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Initially collapsed - output hidden
        output_container = footer_shell.query_one("#shell-output-container")
        assert output_container.styles.display == "none"

        # Expand shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Output should be visible when expanded
        assert output_container.styles.display == "block"

        # Collapse shell
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Output should be hidden when collapsed
        assert output_container.styles.display == "none"


@pytest.mark.asyncio
async def test_footer_shell_welcome_message():
    """Test that welcome message appears on first expansion."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Initially no output
        assert len(footer_shell._output_lines) == 0

        # Expand shell for the first time
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # Welcome message should appear
        assert len(footer_shell._output_lines) > 0
        output_text = "".join(footer_shell._output_lines)
        assert "Welcome" in output_text or "Grind" in output_text


@pytest.mark.asyncio
async def test_footer_shell_clear_command():
    """Test that clear command works."""
    app = AgentTUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        footer_shell = app.query_one("#footer-shell", FooterShell)

        # Expand and add some output
        await pilot.press("ctrl+grave_accent")
        await pilot.pause()

        # There should be welcome message
        assert len(footer_shell._output_lines) > 0

        # Clear the output
        shell_input = footer_shell.query_one("#shell-input")
        shell_input.value = "clear"
        await pilot.press("enter")
        await pilot.pause()

        # Output should be cleared
        assert len(footer_shell._output_lines) == 0
