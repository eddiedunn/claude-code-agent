"""Claude Code hooks configuration generator.

Claude Code has a native hook system configured in settings.json.
Hooks fire shell commands at lifecycle events:
- session_start: when a new Claude Code session begins
- pre_tool_use: before any tool executes
- post_tool_use: after any tool executes

Dan's approach: hooks POST events to an observability server.
This module generates the settings.json hook configuration that
makes Claude Code send events to our observer server.

The hooks use curl to POST JSON payloads. This keeps the hook
commands simple and dependency-free — curl is available everywhere.

Usage:
    from grind.hooks_config import generate_hooks_config, install_hooks

    # Generate the config dict
    config = generate_hooks_config(observer_url="http://localhost:8421")

    # Install into Claude Code settings
    install_hooks(config)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_OBSERVER_URL = "http://localhost:8421"


def generate_hooks_config(
    observer_url: str | None = None,
) -> dict:
    """Generate Claude Code settings.json hook entries.

    These hooks fire curl commands that POST event data to the
    observer server. Claude Code passes event data via environment
    variables and stdin.

    Args:
        observer_url: Observer server URL. Defaults to GRIND_OBSERVER_URL
                      env var or http://localhost:8421

    Returns:
        Dict suitable for merging into .claude/settings.json
    """
    url = observer_url or os.environ.get("GRIND_OBSERVER_URL", DEFAULT_OBSERVER_URL)
    events_endpoint = f"{url}/events"

    return {
        "hooks": {
            "session_start": [
                {
                    "type": "command",
                    "command": _build_hook_command("session_start", events_endpoint),
                }
            ],
            "pre_tool_use": [
                {
                    "type": "command",
                    "command": _build_hook_command("pre_tool_use", events_endpoint),
                }
            ],
            "post_tool_use": [
                {
                    "type": "command",
                    "command": _build_hook_command("post_tool_use", events_endpoint),
                }
            ],
        }
    }


def _build_hook_command(event_type: str, endpoint: str) -> str:
    """Build the curl command for a hook.

    Claude Code hooks receive event data on stdin as JSON.
    We pipe that through to the observer server with the event type added.

    The command uses jq to add the event_type field to the stdin JSON,
    then posts it to the observer. Falls back to a simpler approach
    if jq isn't available.
    """
    # Use a shell script that reads stdin, adds event_type, and posts
    # This approach works whether or not jq is installed
    return (
        f'python3 -c "'
        f"import sys, json, urllib.request; "
        f"data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {{}}; "
        f"data['event_type'] = '{event_type}'; "
        f"req = urllib.request.Request("
        f"'{endpoint}', "
        f"data=json.dumps(data).encode(), "
        f"headers={{'Content-Type': 'application/json'}}); "
        f"urllib.request.urlopen(req)"
        f'" 2>/dev/null || true'
    )


def get_settings_path(project_dir: str | None = None) -> Path:
    """Get the path to Claude Code settings.json.

    Checks project-level first, then user-level.

    Args:
        project_dir: Project directory to check for .claude/settings.json

    Returns:
        Path to the settings file (may not exist yet)
    """
    if project_dir:
        project_settings = Path(project_dir) / ".claude" / "settings.json"
        if project_settings.exists():
            return project_settings

    # User-level settings
    return Path.home() / ".claude" / "settings.json"


def install_hooks(
    hooks_config: dict,
    project_dir: str | None = None,
    merge: bool = True,
) -> Path:
    """Install hook configuration into Claude Code settings.

    Args:
        hooks_config: Config dict from generate_hooks_config()
        project_dir: Install to project-level settings if provided
        merge: If True, merge with existing settings. If False, overwrite hooks section.

    Returns:
        Path to the modified settings file
    """
    if project_dir:
        settings_path = Path(project_dir) / ".claude" / "settings.json"
    else:
        settings_path = Path.home() / ".claude" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    existing = {}
    if settings_path.exists():
        existing = json.loads(settings_path.read_text())

    if merge and "hooks" in existing:
        # Merge: add our hooks alongside existing ones
        for hook_type, hook_list in hooks_config["hooks"].items():
            if hook_type in existing["hooks"]:
                # Check if our hook is already installed (avoid duplicates)
                existing_cmds = {
                    h.get("command", "") for h in existing["hooks"][hook_type]
                }
                for hook in hook_list:
                    if hook.get("command", "") not in existing_cmds:
                        existing["hooks"][hook_type].append(hook)
            else:
                existing["hooks"][hook_type] = hook_list
    else:
        existing["hooks"] = hooks_config["hooks"]

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    return settings_path


def uninstall_hooks(project_dir: str | None = None) -> bool:
    """Remove grind observer hooks from Claude Code settings.

    Identifies our hooks by the observer URL pattern and removes them.

    Returns:
        True if hooks were found and removed
    """
    settings_path = get_settings_path(project_dir)
    if not settings_path.exists():
        return False

    settings = json.loads(settings_path.read_text())
    if "hooks" not in settings:
        return False

    modified = False
    for hook_type in ["session_start", "pre_tool_use", "post_tool_use"]:
        if hook_type in settings["hooks"]:
            original_len = len(settings["hooks"][hook_type])
            settings["hooks"][hook_type] = [
                h for h in settings["hooks"][hook_type]
                if "grind" not in h.get("command", "").lower()
                and "/events" not in h.get("command", "")
            ]
            if len(settings["hooks"][hook_type]) < original_len:
                modified = True
            if not settings["hooks"][hook_type]:
                del settings["hooks"][hook_type]

    if modified:
        if not settings["hooks"]:
            del settings["hooks"]
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    return modified


def print_hooks_config(observer_url: str | None = None) -> None:
    """Print the hooks configuration for manual installation.

    Useful if the user wants to see what would be installed
    before committing.
    """
    config = generate_hooks_config(observer_url)
    print(json.dumps(config, indent=2))
