"""Tests for async_helpers utilities."""

import asyncio

import pytest

from tests.utils.async_helpers import (
    collect_async_generator,
    run_with_timeout,
    wait_for_condition,
)


@pytest.mark.asyncio
async def test_run_with_timeout_success():
    """Test that run_with_timeout succeeds when coroutine completes in time."""
    async def slow_coro():
        await asyncio.sleep(0.1)
        return "done"

    result = await run_with_timeout(slow_coro(), timeout_sec=1.0)
    assert result == "done"


@pytest.mark.asyncio
async def test_run_with_timeout_timeout():
    """Test that run_with_timeout raises TimeoutError when timeout is exceeded."""
    async def slow_coro():
        await asyncio.sleep(1.0)
        return "done"

    with pytest.raises(asyncio.TimeoutError):
        await run_with_timeout(slow_coro(), timeout_sec=0.1)


@pytest.mark.asyncio
async def test_collect_async_generator():
    """Test that collect_async_generator collects all items."""
    async def test_gen():
        for i in range(5):
            yield i

    items = await collect_async_generator(test_gen())
    assert items == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_wait_for_condition_success():
    """Test that wait_for_condition succeeds when condition becomes true."""
    condition_flag = [False]

    async def set_condition():
        await asyncio.sleep(0.1)
        condition_flag[0] = True

    # Run condition setter in background
    task = asyncio.create_task(set_condition())
    await wait_for_condition(
        lambda: condition_flag[0], timeout_sec=1.0, poll_interval=0.01
    )
    await task


@pytest.mark.asyncio
async def test_wait_for_condition_timeout():
    """Test that wait_for_condition raises TimeoutError when condition is not met."""
    with pytest.raises(asyncio.TimeoutError):
        await wait_for_condition(
            lambda: False, timeout_sec=0.1, poll_interval=0.01
        )
