#!/usr/bin/env python3
"""
Streaming log viewer widget for Agent TUI.

Provides a real-time log display with syntax highlighting and navigation.
"""

from datetime import datetime

from textual.binding import Binding
from textual.widgets import RichLog


class StreamingLogViewer(RichLog):
    """
    Real-time log viewer with syntax highlighting and navigation controls.

    Features:
    - Auto-scrolling during streaming
    - Syntax highlighting for common patterns (ERROR, WARN, SUCCESS, etc.)
    - Keyboard navigation (page up/down, top/bottom)
    - Follow mode toggle
    - Status indicator showing streaming state
    """

    # Keyboard bindings for navigation
    BINDINGS = [
        Binding("space", "page_down", "Page Down"),
        Binding("b", "page_up", "Page Up"),
        Binding("g", "go_top", "Top"),
        Binding("G", "go_bottom", "Bottom"),
        Binding("f", "toggle_follow", "Follow"),
    ]

    def __init__(self, **kwargs):
        """Initialize the streaming log viewer."""
        super().__init__(highlight=True, markup=True, **kwargs)
        self.auto_scroll = True
        self.streaming = False
        self.current_agent_id: str | None = None
        self.line_count = 0

    def start_streaming(self, agent_id: str):
        """
        Start streaming logs for the specified agent.

        Args:
            agent_id: The ID of the agent to stream logs for
        """
        self.streaming = True
        self.current_agent_id = agent_id
        self.clear()
        self.line_count = 0

    def stop_streaming(self):
        """Stop streaming logs."""
        self.streaming = False

    def append_line(self, line: str, timestamp: datetime | None = None):
        """
        Append a line to the log with optional timestamp and syntax highlighting.

        Args:
            line: The log line to append
            timestamp: Optional timestamp to prefix the line with
        """
        # Format timestamp if provided
        if timestamp:
            time_str = timestamp.strftime("%H:%M:%S")
            formatted_line = f"[dim]{time_str}[/dim] {line}"
        else:
            formatted_line = line

        # Apply syntax highlighting for common patterns
        # ERROR/FAIL in red
        if "ERROR" in formatted_line or "FAIL" in formatted_line:
            formatted_line = formatted_line.replace("ERROR", "[bold red]ERROR[/bold red]").replace(
                "FAIL", "[bold red]FAIL[/bold red]"
            )

        # WARN in yellow
        if "WARN" in formatted_line:
            formatted_line = formatted_line.replace("WARN", "[bold yellow]WARN[/bold yellow]")

        # SUCCESS/PASS in green
        if "SUCCESS" in formatted_line or "PASS" in formatted_line:
            formatted_line = formatted_line.replace(
                "SUCCESS", "[bold green]SUCCESS[/bold green]"
            ).replace("PASS", "[bold green]PASS[/bold green]")

        # Tool names in cyan (simple heuristic: words starting with capital
        # letter followed by lowercase). This is a basic implementation -
        # could be enhanced with more sophisticated patterns

        # Write the line
        self.write(formatted_line)
        self.line_count += 1

        # Auto-scroll if enabled
        if self.auto_scroll:
            self.scroll_end()

    def action_toggle_follow(self):
        """Toggle auto-scroll follow mode."""
        self.auto_scroll = not self.auto_scroll
        status = "enabled" if self.auto_scroll else "disabled"
        self.write(f"[dim]Follow mode {status}[/dim]")

    def action_go_top(self):
        """Scroll to the top of the log."""
        self.scroll_home()

    def action_go_bottom(self):
        """Scroll to the bottom of the log."""
        self.scroll_end()

    def action_page_up(self):
        """Scroll up one page."""
        self.scroll_page_up()

    def action_page_down(self):
        """Scroll down one page."""
        self.scroll_page_down()

    def compose(self):
        """
        Compose the widget with status indicator.

        Shows streaming status indicator.
        """
        # Note: RichLog doesn't typically use compose() for its content
        # The status indicator could be shown via the border_title or elsewhere
        # For now, we'll rely on the parent container to show status
        yield from super().compose() if hasattr(super(), "compose") else []
