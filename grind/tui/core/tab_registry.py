"""
Tab Registry for Agent TUI.

Provides configuration-driven tab management with keyboard bindings,
compose functions, and lifecycle callbacks.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding


@dataclass
class TabConfig:
    """Configuration for a tab in the TUI.

    Attributes:
        id: Unique tab identifier (e.g., "tab-agents")
        title: Display title for the tab
        key: Keyboard shortcut (e.g., "1" or "ctrl+1")
        action_name: Textual action name for switching to this tab
        binding_description: Short label for footer display
        compose_fn: Function returning ComposeResult for tab content
        on_mount_fn: Optional callback when tab is mounted
        on_unmount_fn: Optional callback when tab is unmounted
        stop_stream_on_leave: Whether to stop streaming when leaving tab
        enabled: Whether the tab is currently enabled
        category: Tab category for grouping ("agents", "monitoring", "logs", "tools")
    """

    id: str
    title: str
    key: str | None = None
    action_name: str | None = None
    binding_description: str | None = None
    compose_fn: Callable[[], ComposeResult] | None = None
    on_mount_fn: Callable[[], Any] | None = None
    on_unmount_fn: Callable[[], None] | None = None
    stop_stream_on_leave: bool = True
    enabled: bool = True
    category: str = "general"

    def get_binding(self) -> Binding | None:
        """Get a Textual Binding for this tab.

        Returns:
            Binding with priority=True for proper key handling, or None if no key configured.
        """
        if not self.key or not self.action_name:
            return None

        return Binding(
            key=self.key,
            action=self.action_name,
            description=self.binding_description or self.title,
            priority=True,  # CRITICAL: Ensures key bindings work properly
        )


class TabRegistry:
    """Registry for managing TUI tabs.

    Provides a configuration-driven approach to tab management, allowing
    tabs to be registered, enabled/disabled, and queried by category.

    Example:
        registry = TabRegistry()
        registry.register(TabConfig(
            id="tab-agents",
            title="Agents",
            key="1",
            action_name="switch_agents",
            category="agents",
        ))
        bindings = registry.get_bindings()
    """

    def __init__(self):
        """Initialize an empty tab registry."""
        self._tabs: dict[str, TabConfig] = {}

    def register(self, config: TabConfig) -> None:
        """Register a tab configuration.

        Args:
            config: TabConfig to register
        """
        self._tabs[config.id] = config

    def register_many(self, configs: list[TabConfig]) -> None:
        """Register multiple tab configurations.

        Args:
            configs: List of TabConfig objects to register
        """
        for config in configs:
            self.register(config)

    def get_tab(self, tab_id: str) -> TabConfig | None:
        """Get a tab configuration by ID.

        Args:
            tab_id: Tab identifier

        Returns:
            TabConfig if found, None otherwise
        """
        return self._tabs.get(tab_id)

    def get_tabs(self, category: str | None = None) -> list[TabConfig]:
        """Get all tabs, optionally filtered by category.

        Args:
            category: Optional category to filter by

        Returns:
            List of TabConfig objects
        """
        if category is None:
            return list(self._tabs.values())
        return [tab for tab in self._tabs.values() if tab.category == category]

    def get_enabled_tabs(self, category: str | None = None) -> list[TabConfig]:
        """Get all enabled tabs, optionally filtered by category.

        Args:
            category: Optional category to filter by

        Returns:
            List of enabled TabConfig objects
        """
        tabs = self.get_tabs(category)
        return [tab for tab in tabs if tab.enabled]

    def get_bindings(self) -> list[Binding]:
        """Get all keyboard bindings from enabled tabs.

        Returns:
            List of Binding objects for all enabled tabs with key bindings
        """
        bindings = []
        for tab in self.get_enabled_tabs():
            binding = tab.get_binding()
            if binding:
                bindings.append(binding)
        return bindings

    def disable_tab(self, tab_id: str) -> None:
        """Disable a tab.

        Args:
            tab_id: Tab identifier to disable
        """
        if tab_id in self._tabs:
            self._tabs[tab_id].enabled = False

    def enable_tab(self, tab_id: str) -> None:
        """Enable a tab.

        Args:
            tab_id: Tab identifier to enable
        """
        if tab_id in self._tabs:
            self._tabs[tab_id].enabled = True

    def count_tabs(self) -> int:
        """Get total number of registered tabs.

        Returns:
            Number of registered tabs
        """
        return len(self._tabs)

    def clear(self) -> None:
        """Clear all registered tabs."""
        self._tabs.clear()
