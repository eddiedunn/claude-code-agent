"""Cost-aware task routing for model selection.

This module provides heuristics-based routing to automatically select the
most appropriate model (haiku, sonnet, or opus) for a given task based on
its complexity and characteristics.
"""

from typing import Literal


class CostAwareRouter:
    """Routes tasks to appropriate models based on complexity heuristics.

    The router analyzes task descriptions using keyword patterns and heuristics
    to classify tasks into three complexity tiers:
    - Simple (haiku): Quick fixes, typos, formatting, simple updates
    - Medium (sonnet): Standard features, refactoring, moderate complexity
    - Complex (opus): Architecture changes, complex features, large refactors

    This helps optimize cost and latency by using the most appropriate model
    for each task's complexity level.
    """

    def __init__(self):
        """Initialize the router with keyword patterns for each complexity tier."""
        # Simple task keywords - quick, straightforward operations
        self.simple_keywords = [
            "typo", "fix typo", "spelling", "format", "formatting",
            "indent", "whitespace", "comment", "add comment",
            "rename variable", "rename file", "delete", "remove",
            "update version", "bump version", "simple fix"
        ]

        # Complex task keywords - architecture, major features
        self.complex_keywords = [
            "architecture", "refactor system", "redesign",
            "migrate", "migration", "implement authentication",
            "implement authorization", "add database", "new feature",
            "complex feature", "optimization", "performance",
            "security", "scale", "distributed", "microservice"
        ]

    def route_task(self, task_description: str) -> Literal["haiku", "sonnet", "opus"]:
        """Route a task to the appropriate model based on complexity analysis.

        Uses keyword matching and heuristic patterns to classify tasks:

        Simple tasks (haiku):
        - Typo fixes and spelling corrections
        - Formatting and indentation changes
        - Adding/updating comments
        - Simple renaming operations
        - Deleting/removing code
        - Version bumps

        Complex tasks (opus):
        - Architecture changes and system redesigns
        - Large-scale refactoring across multiple files
        - New authentication/authorization systems
        - Database integration and migrations
        - Performance optimization
        - Security implementations
        - Distributed system features

        Medium tasks (sonnet):
        - Everything else that doesn't match simple or complex patterns
        - Standard feature additions
        - Bug fixes with moderate complexity
        - Typical development tasks

        Args:
            task_description: The task description string to analyze

        Returns:
            Model name: "haiku" for simple, "sonnet" for medium, "opus" for complex

        Examples:
            >>> router = CostAwareRouter()
            >>> router.route_task("fix typo in README")
            'haiku'
            >>> router.route_task("add new API endpoint")
            'sonnet'
            >>> router.route_task("migrate authentication to OAuth2")
            'opus'
        """
        task_lower = task_description.lower().strip()

        # Check for simple task patterns
        for keyword in self.simple_keywords:
            if keyword in task_lower:
                return "haiku"

        # Check for complex task patterns
        for keyword in self.complex_keywords:
            if keyword in task_lower:
                return "opus"

        # Default to medium complexity (sonnet)
        return "sonnet"
