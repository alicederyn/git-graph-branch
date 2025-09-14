import asyncio
from unittest.mock import Mock

POSITIVE_TIMEOUT = 2.0
NEGATIVE_TIMEOUT = 0.25


async def flush_setup_events() -> None:
    """Ensure we don't get an event from the file creation."""
    await asyncio.sleep(0.1)


async def assert_called_async(fn: Mock) -> None:
    """Assert that fn is called, with a large timeout window to avoid flakes.

    Replaces the mock's side effect.
    """
    called = asyncio.Event()
    fn.side_effect = lambda *_args, **_kwargs: called.set()
    try:
        await asyncio.wait_for(called.wait(), POSITIVE_TIMEOUT)
    except TimeoutError:
        pass
    fn.side_effect = None
    fn.assert_called()
