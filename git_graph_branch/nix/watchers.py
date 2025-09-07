from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from itertools import chain, repeat

from .console import flush_io_on_shutdown
from .contextvars import live_nixer
from .loop import NixLoop
from .polling import PollingNixer


@asynccontextmanager
async def watcher(
    poll_every: timedelta,
) -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Retrigger logic when filesystem changes are detected."""
    nixer = PollingNixer(poll_every)
    with flush_io_on_shutdown(), live_nixer(nixer):
        async with AsyncExitStack() as stack:
            loop = NixLoop(stack, nixer.poll_loop)
            yield loop.needs_refresh


@asynccontextmanager
async def once() -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Run logic once."""
    true_once = iter(chain((True,), repeat(False)))

    async def run_once() -> bool:
        return next(true_once)

    yield run_once
