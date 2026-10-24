import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import ExitStack, asynccontextmanager
from datetime import timedelta
from typing import Literal

from .fact import (
    release_moot_facts,
    report_calculation,
    run_background_task,
    session,
    when_safe_to_nix,
)
from .files import nix_changed_file_states, track_file_changes


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
        when_safe_to_nix(nix_changed_file_states)


class NixLoop:
    def __init__(self, stack: ExitStack) -> None:
        self._stack = stack
        self._nixed: asyncio.Event | None = None

    async def needs_refresh(self) -> Literal[True]:
        self._stack.close()
        if self._nixed:
            release_moot_facts()
            await self._nixed.wait()
        self._nixed = asyncio.Event()
        report = self._stack.enter_context(report_calculation())
        report.on_nix(self._nixed.set)
        return True


@asynccontextmanager
async def watcher(
    poll_every: timedelta,
) -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Retrigger logic when filesystem changes are detected."""
    await_changes_and_nix = efficient_await_and_nix_impl() or (
        lambda until: poll_for_changes(poll_every, until)
    )
    async with asyncio.TaskGroup() as task_group:
        with session(task_group), ExitStack() as stack:
            run_background_task(track_file_changes(await_changes_and_nix))
            yield NixLoop(stack).needs_refresh


@asynccontextmanager
async def once() -> AsyncGenerator[Callable[[], Coroutine[None, None, bool]], None]:
    """Run logic once."""
    with session(None), ExitStack() as stack:
        started = False

        async def run_once() -> bool:
            nonlocal started
            if started:
                stack.close()
                return False
            started = True
            stack.enter_context(report_calculation())
            return True

        yield run_once
