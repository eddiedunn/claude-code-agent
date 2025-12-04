"""Tests for hook trigger logic validation in SlashCommandHook.should_run()."""

import pytest

from grind.models import HookTrigger, SlashCommandHook


class TestHookTriggerEvery:
    """Tests for HookTrigger.EVERY behavior."""

    def test_hook_trigger_every_runs_all_iterations(self):
        """Test that EVERY trigger runs for all iterations."""
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.EVERY)

        # Test iterations 1-10
        for i in range(1, 11):
            assert hook.should_run(i, False) is True


class TestHookTriggerEveryN:
    """Tests for HookTrigger.EVERY_N behavior."""

    def test_hook_trigger_every_n_runs_modulo_n(self):
        """Test that EVERY_N trigger runs only at multiples of trigger_count."""
        hook = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=3
        )

        # Test iterations 1-10
        expected_runs = {3, 6, 9}
        for i in range(1, 11):
            if i in expected_runs:
                assert hook.should_run(i, False) is True, f"Should run at iteration {i}"
            else:
                assert hook.should_run(i, False) is False, f"Should not run at iteration {i}"


class TestHookTriggerOnce:
    """Tests for HookTrigger.ONCE behavior."""

    def test_hook_trigger_once_runs_iteration_1_only(self):
        """Test that ONCE trigger only runs at iteration 1."""
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.ONCE)

        # Should run at iteration 1
        assert hook.should_run(1, False) is True

        # Should not run at iterations 2, 3
        assert hook.should_run(2, False) is False
        assert hook.should_run(3, False) is False


class TestHookTriggerOnError:
    """Tests for HookTrigger.ON_ERROR behavior."""

    def test_hook_trigger_on_error_condition(self):
        """Test that ON_ERROR trigger only runs when is_error=True."""
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.ON_ERROR)

        # Should run when is_error=True
        assert hook.should_run(1, is_error=True) is True

        # Should not run when is_error=False
        assert hook.should_run(1, is_error=False) is False


class TestHookTriggerOnSuccess:
    """Tests for HookTrigger.ON_SUCCESS behavior.

    Note: ON_SUCCESS is defined in the HookTrigger enum but not currently
    implemented in the should_run() method. This test validates that the enum
    value exists and can be instantiated, but should_run() returns False for it
    since there's no handling clause for it.
    """

    def test_hook_trigger_on_success_returns_false(self):
        """Test that ON_SUCCESS trigger currently returns False (not implemented)."""
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.ON_SUCCESS)

        # ON_SUCCESS is in the enum but not implemented in should_run()
        # so it falls through to the final return False
        assert hook.should_run(1, is_error=False) is False
        assert hook.should_run(1, is_error=True) is False


class TestHookTriggerBoundaryCases:
    """Tests for boundary conditions and edge cases."""

    def test_hook_every_n_boundary_cases(self):
        """Test EVERY_N with boundary conditions."""
        # Test trigger_count=1 (should run every iteration)
        hook_count_1 = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=1
        )
        for i in range(1, 6):
            assert hook_count_1.should_run(i, False) is True, f"trigger_count=1 should run at iteration {i}"

        # Test trigger_count=100 (should run only at iteration 100)
        hook_count_100 = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=100
        )
        assert hook_count_100.should_run(100, False) is True
        assert hook_count_100.should_run(50, False) is False
        assert hook_count_100.should_run(99, False) is False
        assert hook_count_100.should_run(200, False) is True

        # Test iteration 0 edge case
        hook_count_5 = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=5
        )
        # iteration 0 % 5 == 0, so it should technically pass the modulo check
        assert hook_count_5.should_run(0, False) is True


class TestHookTriggerEnumValues:
    """Tests to ensure all enum values are tested."""

    def test_all_trigger_enum_values_work(self):
        """Test that all HookTrigger enum values can be instantiated."""
        # Create hooks with each trigger type
        hook_every = SlashCommandHook(command="/test", trigger=HookTrigger.EVERY)
        hook_every_n = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=2
        )
        hook_once = SlashCommandHook(command="/test", trigger=HookTrigger.ONCE)
        hook_on_error = SlashCommandHook(command="/test", trigger=HookTrigger.ON_ERROR)
        hook_on_success = SlashCommandHook(command="/test", trigger=HookTrigger.ON_SUCCESS)

        # All should be valid and callable
        assert hook_every.should_run(1, False) is True
        assert hook_every_n.should_run(1, False) is False
        assert hook_once.should_run(1, False) is True
        assert hook_on_error.should_run(1, is_error=True) is True
        # ON_SUCCESS is in the enum but not implemented, returns False
        assert hook_on_success.should_run(1, is_error=False) is False


class TestHookTriggerStringConversion:
    """Tests for string-to-enum conversion in SlashCommandHook."""

    def test_hook_trigger_string_conversion(self):
        """Test that trigger can be specified as string and is converted to enum."""
        hook_string = SlashCommandHook(command="/test", trigger="once")
        hook_enum = SlashCommandHook(command="/test", trigger=HookTrigger.ONCE)

        # Both should behave identically
        assert hook_string.should_run(1, False) == hook_enum.should_run(1, False)
        assert hook_string.should_run(2, False) == hook_enum.should_run(2, False)


class TestHookTriggerMultipleIterations:
    """Tests for trigger behavior across multiple iterations."""

    def test_every_n_across_many_iterations(self):
        """Test EVERY_N across a larger range of iterations."""
        hook = SlashCommandHook(
            command="/test",
            trigger=HookTrigger.EVERY_N,
            trigger_count=7
        )

        # Should run at 7, 14, 21, 28, etc.
        expected_runs = {7, 14, 21, 28, 35, 42, 49}
        for i in range(1, 51):
            if i in expected_runs:
                assert hook.should_run(i, False) is True, f"Should run at iteration {i}"
            else:
                assert hook.should_run(i, False) is False, f"Should not run at iteration {i}"

    def test_on_error_across_iterations(self):
        """Test ON_ERROR trigger across multiple iterations with varying error states."""
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.ON_ERROR)

        # Simulate alternating error conditions
        for i in range(1, 6):
            is_error = (i % 2 == 0)  # Error on even iterations
            result = hook.should_run(i, is_error=is_error)
            assert result == is_error, f"Iteration {i}: expected {is_error}, got {result}"

    def test_on_success_across_iterations(self):
        """Test ON_SUCCESS trigger across multiple iterations.

        Note: ON_SUCCESS is defined in the enum but not implemented in should_run(),
        so it always returns False regardless of is_error value.
        """
        hook = SlashCommandHook(command="/test", trigger=HookTrigger.ON_SUCCESS)

        # ON_SUCCESS is not implemented, so should always return False
        for i in range(1, 6):
            is_error = (i % 2 == 0)  # Error on even iterations
            result = hook.should_run(i, is_error=is_error)
            assert result is False, f"Iteration {i}: ON_SUCCESS should return False, got {result}"
