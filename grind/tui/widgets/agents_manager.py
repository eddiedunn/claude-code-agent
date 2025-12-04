#!/usr/bin/env python3
"""
Agents manager for Grind TUI.

Handles displaying and managing running and completed agents lists.
"""

import logging

from textual.widgets import DataTable, ListView

from grind.tui.core.models import AgentInfo, AgentStatus

from .list_items import AgentListItem

logger = logging.getLogger(__name__)


class RunningAgentsManager:
    """
    Manages the running agents list view.

    Displays agents with PENDING, RUNNING, or PAUSED status in a ListView with
    real-time status indicators and progress feedback.
    """

    def __init__(self, list_view: ListView):
        """
        Initialize running agents manager.

        Args:
            list_view: The ListView widget for running agents
        """
        self.list_view = list_view
        self.agents: list[AgentInfo] = []

    def update(self, all_agents: list[AgentInfo]):
        """
        Update the running agents list.

        Args:
            all_agents: Complete list of all agents (will filter to running)
        """
        if not self.list_view.is_attached:
            logger.debug("Running agents list view not attached")
            return

        self.list_view.clear()

        # Filter to running/pending/paused agents
        self.agents = [
            a
            for a in all_agents
            if a.status in (AgentStatus.PENDING, AgentStatus.RUNNING, AgentStatus.PAUSED)
        ]

        logger.debug(f"Displaying {len(self.agents)} running agents")

        for agent in self.agents:
            self.list_view.append(AgentListItem(agent))

    def get_count(self) -> int:
        """Get count of running agents."""
        return len(self.agents)


class CompletedAgentsManager:
    """
    Manages the completed agents DataTable.

    Displays agents with COMPLETE, STUCK, FAILED, or CANCELLED status in a sortable
    table with columns for time, status, type, task, duration, and model.
    """

    def __init__(self, table: DataTable):
        """
        Initialize completed agents manager.

        Args:
            table: The DataTable widget for completed agents
        """
        self.table = table
        self.agents: list[AgentInfo] = []
        self.filtered_agents: list[AgentInfo] = []
        self._columns_initialized = False

    def _initialize_columns(self):
        """Initialize table columns (called once)."""
        if self._columns_initialized:
            return

        self.table.add_column("Time", key="time", width=10)
        self.table.add_column("Status", key="status", width=12)
        self.table.add_column("Type", key="type", width=10)
        self.table.add_column("Task", key="task")
        self.table.add_column("Duration", key="duration", width=10)
        self.table.add_column("Model", key="model", width=8)

        self._columns_initialized = True

    def update(self, all_agents: list[AgentInfo]):
        """
        Update the completed agents table.

        Args:
            all_agents: Complete list of all agents (will filter to completed)
        """
        if not self.table.is_attached:
            logger.debug("Completed agents table not attached")
            return

        # Initialize columns on first update
        if not self._columns_initialized:
            self._initialize_columns()

        # Clear existing rows
        self.table.clear()

        # Filter to completed agents
        completed = [
            a
            for a in all_agents
            if a.status
            in (
                AgentStatus.COMPLETE,
                AgentStatus.STUCK,
                AgentStatus.FAILED,
                AgentStatus.CANCELLED,
            )
        ]

        # Use filtered agents if active, otherwise show all
        agents_to_show = self.filtered_agents if self.filtered_agents else completed

        logger.debug(
            f"Displaying {len(agents_to_show)} completed agents (total completed: {len(completed)})"
        )

        # Sort by completion time (newest first)
        sorted_agents = sorted(
            agents_to_show,
            key=lambda a: (
                a.completed_at if a.completed_at else a.started_at if a.started_at else a.created_at
            ),
            reverse=True,
        )

        # Add rows
        for agent in sorted_agents:
            self._add_agent_row(agent)

    def _add_agent_row(self, agent: AgentInfo):
        """
        Add an agent row to the table.

        Args:
            agent: Agent to add
        """
        # Format timestamp
        time_str = (
            agent.completed_at.strftime("%H:%M:%S")
            if agent.completed_at
            else agent.started_at.strftime("%H:%M:%S")
            if agent.started_at
            else agent.created_at.strftime("%H:%M:%S")
        )

        # Format status with icon
        if agent.status == AgentStatus.COMPLETE:
            status_str = "+ Complete"
        elif agent.status == AgentStatus.FAILED:
            status_str = "X Failed"
        elif agent.status == AgentStatus.STUCK:
            status_str = "! Stuck"
        else:
            status_str = "- Cancelled"

        # Format duration
        duration_str = agent.duration if agent.duration else "-"

        # Truncate task description for table display
        if len(agent.task_description) > 50:
            task_str = agent.task_description[:50] + "..."
        else:
            task_str = agent.task_description

        # Add row
        self.table.add_row(
            time_str,
            status_str,
            agent.agent_type.value.capitalize(),
            task_str,
            duration_str,
            agent.model,
            key=agent.agent_id,  # Use agent_id as row key for selection
        )

    def filter_agents(self, search_term: str, all_agents: list[AgentInfo]):
        """
        Filter agents by search term.

        Args:
            search_term: Search term to filter by
            all_agents: Complete list of all agents
        """
        completed = [
            a
            for a in all_agents
            if a.status
            in (
                AgentStatus.COMPLETE,
                AgentStatus.STUCK,
                AgentStatus.FAILED,
                AgentStatus.CANCELLED,
            )
        ]

        if not search_term:
            self.filtered_agents = []
        else:
            term_lower = search_term.lower()
            self.filtered_agents = [
                a
                for a in completed
                if term_lower in a.task_description.lower()
                or term_lower in a.agent_type.value.lower()
                or term_lower in a.model.lower()
            ]

        self.update(all_agents)

    def clear_filter(self, all_agents: list[AgentInfo]):
        """
        Clear the search filter.

        Args:
            all_agents: Complete list of all agents
        """
        self.filtered_agents = []
        self.update(all_agents)

    def get_count(self) -> int:
        """Get count of completed agents."""
        return len(self.agents)

    def is_filtered(self) -> bool:
        """Check if filtering is active."""
        return bool(self.filtered_agents)
