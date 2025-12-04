"""List item widgets for displaying agents."""

from textual.widgets import ListItem, Static

from grind.tui.core.models import AgentInfo, AgentStatus


class AgentListItem(ListItem):
    """List item widget for displaying agent information."""

    def __init__(self, agent: AgentInfo):
        """Initialize the agent list item.

        Args:
            agent: The AgentInfo object to display
        """
        super().__init__()
        self.agent = agent

    def compose(self):
        """Compose the list item with formatted agent information."""
        icon = self._get_status_icon()
        status = self.agent.status.value
        agent_type = self.agent.agent_type.value
        task_preview = self._truncate_task(self.agent.task_description, 40)
        progress = self._format_progress()
        duration = self._format_duration()

        # Format: "{icon} {status:10} {type:12} {task_preview:40} ({progress}%) [{duration}]"
        content = f"{icon} {status:10} {agent_type:12} {task_preview:40} ({progress}) [{duration}]"

        yield Static(content)

    def _get_status_icon(self) -> str:
        """Get the styled icon for the agent's current status.

        Returns:
            Rich markup string with icon and styling
        """
        status_map = {
            AgentStatus.PENDING: "[dim]P[/dim]",
            AgentStatus.RUNNING: "[bold yellow]>[/bold yellow]",
            AgentStatus.PAUSED: "[bold magenta]?[/bold magenta]",
            AgentStatus.COMPLETE: "[green]+[/green]",
            AgentStatus.STUCK: "[bold red]![/bold red]",
            AgentStatus.FAILED: "[red]X[/red]",
            AgentStatus.CANCELLED: "[dim]-[/dim]",
        }
        return status_map.get(self.agent.status, "?")

    def _format_duration(self) -> str:
        """Format the agent's duration in a compact form.

        Returns:
            String like "2m 34s" or "45s"
        """
        return self.agent.duration

    def _format_progress(self) -> str:
        """Format the agent's progress.

        Returns:
            String like "80%" or iteration count
        """
        if self.agent.status in (AgentStatus.COMPLETE, AgentStatus.FAILED, AgentStatus.CANCELLED):
            # Show percentage for completed agents
            return f"{int(self.agent.progress * 100)}%"
        else:
            # Show iteration count for active agents
            return f"{self.agent.iteration}/{self.agent.max_iterations}"

    def _truncate_task(self, task: str, max_length: int) -> str:
        """Truncate task description to max length with ellipsis.

        Args:
            task: The task description to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated string with ellipsis if needed
        """
        if len(task) <= max_length:
            return task.ljust(max_length)
        return task[: max_length - 3] + "..."
