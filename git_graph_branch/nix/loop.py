import asyncio
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from typing import Any, Literal

from .cohort import Cohort
from .console import flush_and_hold_io
from .contextvars import live_cohort_context


async def await_first_and_cancel(*coros: Coroutine[None, Any, Any]) -> None:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(c) for c in coros]
        _complete, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()


class NixLoop:
    def __init__(
        self,
        stack: AsyncExitStack,
        active_poll: Callable[[], Coroutine[None, Any, Any]],
    ) -> None:
        self._stack = stack
        self._active_poll = active_poll
        self._nixed = asyncio.Event()
        self._reset_cohort()
        self._first_iteration = True

    def _reset_cohort(self) -> None:
        self._cohort = Cohort(nix=self._nixed.set)
        self._stack.enter_context(live_cohort_context(self._cohort))

    async def needs_refresh(self) -> Literal[True]:
        if self._first_iteration:
            self._first_iteration = False
            return True

        flush_and_hold_io()

        await await_first_and_cancel(self._active_poll(), self._nixed.wait())
        self._nixed.clear()
        await self._stack.aclose()
        self._reset_cohort()
        return True
