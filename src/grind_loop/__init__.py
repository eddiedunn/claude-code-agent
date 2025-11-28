"""
Grind Loop - Automated fix-verify loops using Claude Agent SDK

This module provides tools for automating repetitive fix-verify cycles
such as fixing unit tests, CI/CD issues, or code quality problems.
"""

from grind_loop.core import grind, GrindResult, GrindStatus

__all__ = ["grind", "GrindResult", "GrindStatus"]
__version__ = "0.1.0"
