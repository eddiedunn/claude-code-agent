"""
CLI entry point for the Agent Orchestration TUI.

Provides a command-line interface for launching the TUI with optional
task file loading and configuration options.
"""

from grind.tui.app import AgentTUI


async def run_tui(task_file: str | None = None, model: str = "sonnet", verbose: bool = False) -> int:
    """
    Launch the Agent Orchestration TUI.

    Args:
        task_file: Optional tasks.yaml to load on startup
        model: Default model for new agents
        verbose: Enable verbose logging

    Returns:
        Exit code (0 success, 1 error)
    """
    app = AgentTUI()
    if task_file:
        # Queue task file for loading after mount
        app.startup_task_file = task_file
    app.default_model = model
    await app.run_async()
    return 0
