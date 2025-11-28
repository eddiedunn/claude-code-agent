#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "claude-agent-sdk>=0.1.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
Standalone grind loop script - run directly with uv:

    uv run grind.py --task "Fix tests" --verify "pytest" --model sonnet
    uv run grind.py decompose -p "Fix all failures" -v "pytest" -o tasks.yaml
    uv run grind.py batch tasks.yaml

For installed usage: uv run grind --task "..." --verify "..." --model sonnet
"""

import sys

if __name__ == "__main__":
    from grind.cli import main
    sys.exit(main())
