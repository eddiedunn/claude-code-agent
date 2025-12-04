#!/usr/bin/env python3
"""
Agent log streaming and management for TUI.

Handles real-time streaming of agent output to UI widgets.
"""

import asyncio
import re
from collections.abc import Callable
from datetime import datetime

import aiofiles

from grind.tui.core.models import AgentInfo


class AgentLogStreamer:
    """Manages real-time log streaming for agents."""

    def __init__(self):
        """Initialize the log streamer."""
        self.active_streams: dict[str, dict] = {}  # agent_id -> stream info

    async def stream_agent_output(
        self,
        agent: AgentInfo,
        callback: Callable[[str, datetime], None],
        poll_interval: float = 0.1,
    ) -> None:
        """
        Stream agent output to callback as lines arrive.

        Polls the output file and sends new lines to the callback.

        Args:
            agent: Agent to stream
            callback: Called with (line, timestamp) for each new line
            poll_interval: How often to check for new lines (seconds)
        """
        if not agent.output_file:
            return

        self.active_streams[agent.agent_id] = {
            "agent": agent,
            "last_pos": 0,
            "active": True,
        }

        try:
            while self.active_streams[agent.agent_id]["active"]:
                if agent.output_file.exists():
                    try:
                        async with aiofiles.open(agent.output_file) as f:
                            # Seek to last position
                            await f.seek(self.active_streams[agent.agent_id]["last_pos"])

                            # Read new lines
                            async for line in f:
                                # Strip newline but keep content
                                line = line.rstrip("\n")
                                if line:
                                    callback(line, datetime.now())

                            # Update position
                            self.active_streams[agent.agent_id]["last_pos"] = await f.tell()

                    except OSError:
                        # File being written, try again
                        pass

                # Wait before checking again
                await asyncio.sleep(poll_interval)

        finally:
            # Mark stream as inactive
            if agent.agent_id in self.active_streams:
                self.active_streams[agent.agent_id]["active"] = False

    def stop_streaming(self, agent_id: str) -> None:
        """Stop streaming an agent."""
        if agent_id in self.active_streams:
            self.active_streams[agent_id]["active"] = False

    async def get_agent_logs(self, agent: AgentInfo) -> str:
        """
        Get complete logs for an agent.

        Args:
            agent: Agent to get logs for

        Returns:
            Complete log text
        """
        if not agent.output_file or not agent.output_file.exists():
            return "No logs available"

        try:
            async with aiofiles.open(agent.output_file) as f:
                return await f.read()
        except OSError as e:
            return f"Error reading logs: {e}"

    def search_logs(self, agent: AgentInfo, pattern: str) -> list[tuple[int, str]]:
        """
        Search agent logs for pattern.

        Args:
            agent: Agent to search
            pattern: Regex pattern to search for

        Returns:
            List of (line_number, line_text) tuples matching pattern
        """
        if not agent.output_file or not agent.output_file.exists():
            return []

        results = []
        try:
            with open(agent.output_file) as f:
                regex = re.compile(pattern, re.IGNORECASE)
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append((line_num, line.rstrip("\n")))
        except (OSError, re.error):
            pass

        return results

    def filter_logs(
        self,
        agent: AgentInfo,
        level: str | None = None,
        start_line: int = 0,
        max_lines: int | None = None,
    ) -> str:
        """
        Get filtered logs (by line range and optional level).

        Args:
            agent: Agent to get logs for
            level: Filter by log level (ERROR, WARN, INFO, DEBUG)
            start_line: Starting line number (0-indexed)
            max_lines: Maximum lines to return (None for all)

        Returns:
            Filtered log text
        """
        if not agent.output_file or not agent.output_file.exists():
            return "No logs available"

        try:
            with open(agent.output_file) as f:
                lines = f.readlines()

            # Filter by level if specified
            if level:
                level_upper = level.upper()
                lines = [line for line in lines if level_upper in line.upper()]

            # Apply line range
            if start_line > 0:
                lines = lines[start_line:]

            if max_lines:
                lines = lines[:max_lines]

            return "".join(lines)

        except OSError:
            return "Error reading logs"

    def get_log_stats(self, agent: AgentInfo) -> dict:
        """
        Get statistics about agent logs.

        Args:
            agent: Agent to analyze

        Returns:
            Dict with log stats (line_count, size_bytes, has_errors, has_warnings)
        """
        if not agent.output_file or not agent.output_file.exists():
            return {
                "line_count": 0,
                "size_bytes": 0,
                "has_errors": False,
                "has_warnings": False,
            }

        try:
            with open(agent.output_file) as f:
                lines = f.readlines()
                content = "".join(lines)

            return {
                "line_count": len(lines),
                "size_bytes": len(content),
                "has_errors": "ERROR" in content,
                "has_warnings": "WARN" in content or "WARNING" in content,
            }

        except OSError:
            return {
                "line_count": 0,
                "size_bytes": 0,
                "has_errors": False,
                "has_warnings": False,
            }
