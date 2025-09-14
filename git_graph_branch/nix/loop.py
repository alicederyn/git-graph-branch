import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from itertools import chain, repeat
from typing import Literal

from .cohort import Cohort, live_cohort_context
from .console import flush_and_hold_io, flush_io_on_shutdown
from .tracking import nix_cohorts_with_changes


def loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    try:
        from .macosx import macosx_event_loop

        return macosx_event_loop
    except ImportError:
        pass
    return None


def efficient_await_and_nix_impl() -> (
    Callable[[asyncio.Event], Coroutine[None, None, None]] | None
):
    try:
        from .macosx import await_changes_and_nix

        return await_changes_and_nix
    except ImportError:
        pass

    try:
        from .linux import await_changes_and_nix

        return await_changes_and_nix
    except ImportError:
        pass

    return None


async def poll_for_changes(poll_every: timedelta, until: asyncio.Event) -> None:
    while not until.is_set():
        await asyncio.sleep(poll_every.total_seconds())
        nix_cohorts_with_changes()


class NixLoop:
    def __init__(
        self,
        stack: AsyncExitStack,
        await_changes_and_nix: Callable[[asyncio.Event], Coroutine[None, None, None]],
    ) -> None:
        self._stack = stack
        self._await_changes_and_nix = await_changes_and_nix
        self._nixed = asyncio.Event()
        self._cohort: Cohort | None = None

    def _reset_cohort(self) -> None:
        self._cohort = Cohort()
        self._cohort.on_nix.append(self._nixed.set)
        self._stack.callback(self._nixed.clear)
        self._stack.callback(self._cohort.nix)
        self._stack.enter_context(live_cohort_context(self._cohort))

    async def needs_refresh(self) -> Literal[True]:
        if self._cohort:
            flush_and_hold_io()
            await self._await_changes_and_nix(self._nixed)
            await self._stack.aclose()
        self._reset_cohort()
        return True


@asynccontextmanager
async def watcher(
    poll_every: timedelta,
) -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Retrigger logic when filesystem changes are detected."""
    await_changes_and_nix = efficient_await_and_nix_impl() or (
        lambda until: poll_for_changes(poll_every, until)
    )
    with flush_io_on_shutdown():
        async with AsyncExitStack() as stack:
            loop = NixLoop(stack, await_changes_and_nix)
            yield loop.needs_refresh


@asynccontextmanager
async def once() -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Run logic once."""
    true_once = iter(chain((True,), repeat(False)))

    async def run_once() -> bool:
        return next(true_once)

    yield run_once
