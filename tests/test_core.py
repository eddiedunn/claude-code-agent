"""
Tests for grind_loop core functionality.
"""

import pytest

from grind_loop.core import GrindStatus


def test_grind_status_values():
    """Test that GrindStatus has expected values."""
    assert GrindStatus.COMPLETE.value == "complete"
    assert GrindStatus.STUCK.value == "stuck"
    assert GrindStatus.MAX_ITERATIONS.value == "max_iterations"
    assert GrindStatus.ERROR.value == "error"
