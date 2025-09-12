import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from itertools import chain, repeat
from typing import Literal

from .cohort import Cohort, live_cohort_context
from .console import flush_and_hold_io, flush_io_on_shutdown
from .polling import nix_cohorts_with_changes


class NixLoop:
    def __init__(
        self,
        stack: AsyncExitStack,
        poll_every: timedelta,
    ) -> None:
        self._stack = stack
        self._poll_every = poll_every
        self._nixed = asyncio.Event()
        self._cohort: Cohort | None = None

    def _reset_cohort(self) -> None:
        self._cohort = Cohort()
        self._cohort.on_nix.append(self._nixed.set)
        self._stack.callback(self._nixed.clear)
        self._stack.callback(self._cohort.nix)
        self._stack.enter_context(live_cohort_context(self._cohort))

    async def poll_loop(self) -> None:
        while not self._nixed.is_set():
            await asyncio.sleep(self._poll_every.total_seconds())
            nix_cohorts_with_changes()

    async def needs_refresh(self) -> Literal[True]:
        if self._cohort:
            flush_and_hold_io()
            await self.poll_loop()
            await self._stack.aclose()
        self._reset_cohort()
        return True


@asynccontextmanager
async def watcher(
    poll_every: timedelta,
) -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Retrigger logic when filesystem changes are detected."""
    with flush_io_on_shutdown():
        async with AsyncExitStack() as stack:
            loop = NixLoop(stack, poll_every)
            yield loop.needs_refresh


@asynccontextmanager
async def once() -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Run logic once."""
    true_once = iter(chain((True,), repeat(False)))

    async def run_once() -> bool:
        return next(true_once)

    yield run_once
