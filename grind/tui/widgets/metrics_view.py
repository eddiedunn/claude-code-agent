#!/usr/bin/env python3
"""
Metrics view widget for Agent TUI.

Displays agent metrics including success rate and average duration from MetricsCollector.
"""

from textual.reactive import reactive
from textual.widgets import Static

from grind.orchestration.metrics import MetricsCollector


class MetricsView(Static):
    """
    Widget displaying agent execution metrics.

    Shows aggregated metrics from MetricsCollector including:
    - Success rate (percentage of successful runs)
    - Average duration (mean execution time per run)
    - Total runs count
    - Average cost (if available)

    Reactive Behavior:
    ==================

    This widget uses Textual's reactive() pattern for automatic UI updates:

    - metrics_collector: When set, triggers re-render with updated metrics
    - selected_agent_id: When changed, updates display for specific agent

    Visual Format:
    ==============

    Agent Metrics
    ─────────────
    Agent: {agent_id}
    Success Rate: {XX.X}%
    Avg Duration: {X.XX}s
    Total Runs: {N}
    Avg Cost: ${X.XXX}

    Usage Example:
    ==============

    # Create metrics view
    metrics_view = MetricsView()

    # Set metrics collector
    metrics_view.metrics_collector = collector

    # Display specific agent metrics
    metrics_view.show_agent("agent_1")

    # Display all metrics summary
    metrics_view.show_all()
    """

    # Reactive properties for auto-updating UI
    metrics_collector: reactive[MetricsCollector | None] = reactive(None)
    selected_agent_id: reactive[str | None] = reactive(None)

    def __init__(self, metrics_collector: MetricsCollector | None = None, **kwargs):
        """
        Initialize the metrics view widget.

        Args:
            metrics_collector: Optional MetricsCollector instance to display metrics from
        """
        super().__init__(**kwargs)
        self.metrics_collector = metrics_collector

    def render(self) -> str:
        """Render the metrics view with current data."""
        if self.metrics_collector is None:
            return "[dim]No metrics collector configured[/dim]"

        # If specific agent is selected, show its metrics
        if self.selected_agent_id:
            return self._render_agent_metrics(self.selected_agent_id)

        # Otherwise show all metrics
        return self._render_all_metrics()

    def _render_agent_metrics(self, agent_id: str) -> str:
        """
        Render metrics for a specific agent.

        Args:
            agent_id: The agent ID to display metrics for

        Returns:
            Formatted string with agent metrics
        """
        if self.metrics_collector is None:
            return "[dim]No metrics available[/dim]"

        metrics = self.metrics_collector.get_metrics(agent_id)

        # Build the output
        lines = []
        lines.append("[bold cyan]Agent Metrics[/bold cyan]")
        lines.append("─" * 40)
        lines.append(f"[bold]Agent:[/bold] {agent_id}")
        lines.append(f"[bold]Success Rate:[/bold] {metrics.success_rate * 100:.1f}%")
        lines.append(f"[bold]Avg Duration:[/bold] {metrics.average_duration:.2f}s")
        lines.append(f"[bold]Total Runs:[/bold] {metrics.total_runs}")

        if metrics.total_cost > 0:
            lines.append(f"[bold]Avg Cost:[/bold] ${metrics.average_cost:.4f}")

        return "\n".join(lines)

    def _render_all_metrics(self) -> str:
        """
        Render summary of all agent metrics.

        Returns:
            Formatted string with all agent metrics
        """
        if self.metrics_collector is None:
            return "[dim]No metrics available[/dim]"

        all_metrics = self.metrics_collector.get_all_metrics()

        if not all_metrics:
            return "[dim]No metrics collected yet[/dim]"

        # Build the output
        lines = []
        lines.append("[bold cyan]All Agent Metrics[/bold cyan]")
        lines.append("─" * 60)

        # Header row
        header = f"{'Agent ID':<20} {'Success Rate':>12} {'Avg Duration':>15} {'Runs':>8}"
        lines.append(f"[bold]{header}[/bold]")
        lines.append("─" * 60)

        # Data rows
        for agent_id, metrics in sorted(all_metrics.items()):
            success_rate = f"{metrics.success_rate * 100:.1f}%"
            avg_duration = f"{metrics.average_duration:.2f}s"
            total_runs = str(metrics.total_runs)

            row = f"{agent_id:<20} {success_rate:>12} {avg_duration:>15} {total_runs:>8}"

            # Color code based on success rate
            if metrics.success_rate >= 0.9:
                row = f"[green]{row}[/green]"
            elif metrics.success_rate >= 0.7:
                row = f"[yellow]{row}[/yellow]"
            elif metrics.total_runs > 0:
                row = f"[red]{row}[/red]"

            lines.append(row)

        return "\n".join(lines)

    def show_agent(self, agent_id: str):
        """
        Display metrics for a specific agent.

        Args:
            agent_id: The agent ID to display metrics for
        """
        self.selected_agent_id = agent_id

    def show_all(self):
        """Display summary of all agent metrics."""
        self.selected_agent_id = None

    def set_metrics_collector(self, collector: MetricsCollector):
        """
        Set the metrics collector to display data from.

        Args:
            collector: MetricsCollector instance
        """
        self.metrics_collector = collector
