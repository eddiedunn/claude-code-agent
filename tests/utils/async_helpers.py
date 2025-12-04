"""Async utility functions for testing async code."""

import asyncio
from typing import Any, AsyncGenerator, Callable, Coroutine


async def run_with_timeout(
    coro: Coroutine[Any, Any, Any], timeout_sec: float
) -> Any:
    """Run a coroutine with a timeout.

    Args:
        coro: The coroutine to run.
        timeout_sec: Timeout in seconds.

    Returns:
        The result of the coroutine.

    Raises:
        asyncio.TimeoutError: If the coroutine does not complete within timeout_sec.
    """
    return await asyncio.wait_for(coro, timeout=timeout_sec)


async def collect_async_generator(gen: AsyncGenerator[Any, None]) -> list[Any]:
    """Collect all items from an async generator into a list.

    Args:
        gen: The async generator to collect from.

    Returns:
        A list containing all items from the async generator.
    """
    items = []
    async for item in gen:
        items.append(item)
    return items


async def wait_for_condition(
    condition_fn: Callable[[], bool],
    timeout_sec: float,
    poll_interval: float = 0.1,
) -> None:
    """Wait for a condition function to return True.

    Polls the condition function at regular intervals until it returns True
    or the timeout is reached.

    Args:
        condition_fn: A callable that returns bool. Called repeatedly until True.
        timeout_sec: Maximum time to wait in seconds.
        poll_interval: Time in seconds between condition checks. Defaults to 0.1.

    Raises:
        asyncio.TimeoutError: If the condition does not become True within timeout_sec.
    """
    start_time = asyncio.get_event_loop().time()
    while True:
        if condition_fn():
            return
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_sec:
            raise asyncio.TimeoutError(
                f"Condition not met within {timeout_sec} seconds"
            )
        await asyncio.sleep(poll_interval)
