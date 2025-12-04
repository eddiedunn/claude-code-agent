#!/usr/bin/env python3
"""
REPL shell widget for Agent TUI.

Provides an interactive shell with command input, output display,
history navigation, and command completion.
"""

import asyncio

from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import Input, Static

from ..core.shell_commands import (
    CommandRegistry,
    ShellContext,
    parse_and_execute,
)


class AgentShell(Container):
    """
    Interactive REPL shell widget.

    Provides:
    - Command input with prompt
    - Scrollable output area
    - Command history navigation (up/down arrows)
    - Tab completion for commands
    - Shell escape with ! prefix
    """

    DEFAULT_CSS = """
    AgentShell {
        height: 1fr;
        width: 1fr;
        background: #1a1a2e;
        layout: vertical;
    }

    AgentShell #shell-output {
        height: 1fr;
        width: 1fr;
        background: #1a1a2e;
        padding: 0 1;
        scrollbar-background: #1a1a2e;
        scrollbar-color: #4a4a6a;
    }

    AgentShell #output-text {
        width: 1fr;
        background: transparent;
        color: #e0e0e0;
    }

    AgentShell #completions-popup {
        display: none;
        width: 1fr;
        height: auto;
        background: #2a2a4e;
        border: solid #4a4a6a;
        padding: 0 1;
        max-height: 10;
    }

    AgentShell #completions-popup.visible {
        display: block;
    }

    AgentShell #prompt-container {
        height: auto;
        width: 1fr;
        background: #1a1a2e;
        padding: 0 1;
    }

    AgentShell #shell-prompt {
        width: auto;
        color: #00ff00;
        text-style: bold;
        background: transparent;
    }

    AgentShell #shell-input {
        width: 1fr;
        background: #1a1a2e;
        color: #e0e0e0;
        border: none;
    }

    AgentShell #shell-input:focus {
        border: none;
    }
    """

    def __init__(
        self,
        command_registry: CommandRegistry | None = None,
        shell_context: ShellContext | None = None,
        **kwargs,
    ):
        """
        Initialize the shell widget.

        Args:
            command_registry: Registry for available commands
            shell_context: Context for command execution
            **kwargs: Additional arguments for Container
        """
        super().__init__(**kwargs)
        self.command_registry = command_registry or CommandRegistry()
        self.shell_context = shell_context
        self.history: list[str] = []
        self.history_index: int = -1
        self._output_lines: list[str] = []
        self._completions: list[str] = []
        self._completion_index: int = -1

    def compose(self):
        """Compose the shell layout."""
        with ScrollableContainer(id="shell-output"):
            yield Static("", id="output-text")
        yield Static("", id="completions-popup")
        with Horizontal(id="prompt-container"):
            yield Static("grind> ", id="shell-prompt")
            yield Input(id="shell-input", placeholder="Enter command...")

    def on_mount(self) -> None:
        """Handle widget mount."""
        self.write_output("Welcome to the Grind Agent Shell. Type 'help' for commands.\n")
        # Focus the input widget so user can start typing immediately
        self.call_later(self._focus_input)

    def _focus_input(self) -> None:
        """Focus the input widget with a slight delay."""
        try:
            input_widget = self.query_one("#shell-input", Input)
            input_widget.focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission."""
        if event.input.id != "shell-input":
            return

        command = event.value.strip()
        if not command:
            return

        # Add to history
        self.history.append(command)
        self.history_index = -1

        # Clear input
        event.input.value = ""

        # Echo command to output
        self.write_output(f"grind> {command}\n", style="bold green")

        # Execute command asynchronously
        asyncio.create_task(self.execute_command(command))

    async def on_key(self, event) -> None:
        """Handle key events for history and completion."""
        input_widget = self.query_one("#shell-input", Input)

        # Allow app-level bindings (tab navigation 1-7, q to quit) to pass through
        if event.key in ("1", "2", "3", "4", "5", "6", "7", "q"):
            return

        # Only handle keys when input is focused
        if not input_widget.has_focus:
            return

        if event.key == "up":
            # Navigate to previous history item
            if self.history:
                if self.history_index == -1:
                    self.history_index = len(self.history) - 1
                elif self.history_index > 0:
                    self.history_index -= 1
                input_widget.value = self.history[self.history_index]
                input_widget.cursor_position = len(input_widget.value)
            event.prevent_default()
            event.stop()

        elif event.key == "down":
            # Navigate to next history item
            if self.history_index != -1:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    input_widget.value = self.history[self.history_index]
                else:
                    self.history_index = -1
                    input_widget.value = ""
                input_widget.cursor_position = len(input_widget.value)
            event.prevent_default()
            event.stop()

        elif event.key == "tab":
            # Trigger completion
            partial = input_widget.value
            completions = self.get_completions(partial)
            if completions:
                if len(completions) == 1:
                    # Single match - insert it
                    input_widget.value = completions[0] + " "
                    input_widget.cursor_position = len(input_widget.value)
                else:
                    # Multiple matches - show popup and cycle
                    self.show_completions(completions)
                    if self._completion_index == -1:
                        self._completion_index = 0
                    else:
                        self._completion_index = (self._completion_index + 1) % len(completions)
                    input_widget.value = completions[self._completion_index]
                    input_widget.cursor_position = len(input_widget.value)
            event.prevent_default()
            event.stop()

        elif event.key == "ctrl+c":
            # Cancel current or clear input
            if input_widget.value:
                input_widget.value = ""
                self._hide_completions()
            else:
                self.write_output("^C\n")
            event.prevent_default()
            event.stop()

        elif event.key == "escape":
            # Hide completions
            self._hide_completions()

        else:
            # Any other key hides completions
            self._hide_completions()
            self._completion_index = -1

    async def execute_command(self, line: str) -> None:
        """
        Execute a command line.

        Args:
            line: The command to execute
        """
        line = line.strip()
        if not line:
            return

        # Handle shell escape
        if line.startswith("!"):
            shell_cmd = line[1:].strip()
            if not shell_cmd:
                self.write_output("Usage: !<command>\n")
                return
            result = await self._execute_shell_escape(shell_cmd)
            self.write_output(result + "\n")
            return

        # Handle clear command specially
        if line == "clear":
            self.clear_output()
            return

        # Execute through command registry
        if self.shell_context:
            result = await parse_and_execute(line, self.command_registry, self.shell_context)
        else:
            # No context - limited commands available
            cmd = self.command_registry.get_command(line.split()[0] if line else "")
            if cmd and cmd.name == "help":
                result = await parse_and_execute(
                    line, self.command_registry, self._create_dummy_context()
                )
            else:
                result = "Shell context not initialized. Limited commands available."

        if result:
            self.write_output(result + "\n")

    async def _execute_shell_escape(self, cmd: str) -> str:
        """
        Execute a shell command via subprocess.

        Args:
            cmd: Shell command to execute

        Returns:
            Command output with exit code
        """
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            output = stdout.decode() if stdout else ""
            if stderr:
                output += stderr.decode()
            if process.returncode != 0:
                output += f"\n[Exit code: {process.returncode}]"
            return output.rstrip() if output else "(no output)"
        except asyncio.TimeoutError:
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error executing command: {e}"

    def _create_dummy_context(self) -> ShellContext:
        """Create a minimal context for help command."""

        return ShellContext(
            session=None,  # type: ignore
            agents=[],
            current_agent_id=None,
            history=self.history,
            variables={},
        )

    def write_output(self, text: str, style: str = "") -> None:
        """
        Write text to the output area.

        Args:
            text: Text to display
            style: Optional Rich markup style
        """
        if style:
            text = f"[{style}]{text}[/{style}]"
        self._output_lines.append(text)

        # Update the output widget
        output_widget = self.query_one("#output-text", Static)
        output_widget.update("".join(self._output_lines))

        # Scroll to bottom
        scroll_container = self.query_one("#shell-output", ScrollableContainer)
        scroll_container.scroll_end(animate=False)

    def clear_output(self) -> None:
        """Clear all output text."""
        self._output_lines = []
        output_widget = self.query_one("#output-text", Static)
        output_widget.update("")

    def get_completions(self, partial: str) -> list[str]:
        """
        Get command completions for partial input.

        Args:
            partial: Partial command string

        Returns:
            List of matching command names
        """
        if not partial:
            return []

        # Only complete the first word (command name)
        parts = partial.split()
        if len(parts) > 1:
            return []

        return self.command_registry.get_completions(partial)

    def show_completions(self, completions: list[str]) -> None:
        """
        Display completion popup with options.

        Args:
            completions: List of completion options
        """
        self._completions = completions
        popup = self.query_one("#completions-popup", Static)
        popup.update("\n".join(completions))
        popup.add_class("visible")

    def _hide_completions(self) -> None:
        """Hide the completions popup."""
        popup = self.query_one("#completions-popup", Static)
        popup.remove_class("visible")
        self._completions = []
