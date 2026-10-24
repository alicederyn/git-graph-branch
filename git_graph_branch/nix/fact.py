"""The dependency graph that nix tracks.

See docs/notes/nix-facts.md for the vocabulary.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from enum import Enum
from typing import Any


class NixError(RuntimeError):
    pass


class _Marker(Enum):
    BACKGROUND = "background task"
    CALLBACK = "when_safe_to_nix callback"


@dataclass(eq=False)
class _Frame:
    fact: Fact
    in_report: bool
    alive: bool = True

    def add_dependency(self, fact: Fact) -> None:
        if not self.alive:
            raise NixError("Calculation has already finished")
        self.fact._dependencies.add(fact)
        fact._dependents.add(self.fact)


_context: ContextVar[_Frame | _Marker | None] = ContextVar("nix_context", default=None)


class _Callback:
    def __init__(
        self, fn: Callable[..., object], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._done = False

    def __call__(self) -> None:
        if not self._done:
            self._done = True
            self._fn(*self._args, **self._kwargs)


def _as_callback(
    fn: Callable[..., object], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> _Callback:
    if isinstance(fn, _Callback) and not args and not kwargs:
        return fn
    return _Callback(fn, args, kwargs)


def _check_not_background() -> None:
    if _context.get() is _Marker.BACKGROUND:
        raise NixError("Background tasks must use when_safe_to_nix")


class _Graph:
    def __init__(self) -> None:
        self.active = False
        self.live: set[Fact] = set()
        """Facts that are neither constant nor moot."""
        self.calculating = False
        self.pending: deque[_Callback] = deque()
        self.current_report: Fact | None = None
        self.task_group: asyncio.TaskGroup | None = None
        self.background_tasks: set[asyncio.Task[None]] = set()


_graph = _Graph()


class Fact:
    """A dependency that nix tracks. It holds no data.

    The fact-finder keeps the data. A fact records which calculations
    depend on that data, so that they can be nixed when it changes, and
    so that the fact-finder can drop the data when nothing needs it.
    Never subclassed.

    Callback registration is chainable:
    ``fact.on_nix(fact.on_moot(self.delete, key))``. A callback runs at most
    once. A callback registered after its event has occurred runs immediately.
    Moot is final.
    """

    def __init__(self) -> None:
        _check_not_background()
        self._nixed = False
        self._moot = False
        self._constant = False
        self._calculated = False
        self._dependencies: set[Fact] = set()
        self._dependents: set[Fact] = set()
        self._on_nix: list[_Callback] = []
        self._on_moot: list[_Callback] = []
        _graph.live.add(self)

    @property
    def nixed(self) -> bool:
        return self._nixed

    @property
    def moot(self) -> bool:
        return self._moot

    def record_use(self) -> None:
        """Make the calculation that is running depend on this fact.

        Allows a fact-finder to return the same fact multiple times. Does
        nothing if this fact is constant.

        Raises NixError outside a report calculation, or if this fact is
        nixed or moot.
        """
        if self._constant:
            return
        _check_not_background()
        if self._nixed or self._moot:
            raise NixError(f"Fact is {'nixed' if self._nixed else 'moot'}")
        frame = _context.get()
        if not isinstance(frame, _Frame) or not frame.in_report:
            raise NixError("Fact used outside a report calculation")
        frame.add_dependency(self)

    def nix(self) -> None:
        """Nix this fact and each calculation that depends on it.

        Raises NixError during a report calculation: use when_safe_to_nix.
        """
        _check_not_background()
        if _graph.calculating:
            raise NixError("Cannot nix during a report calculation")
        to_nix: list[Fact] = [self]
        while to_nix:
            fact = to_nix.pop()
            if fact._nixed or fact._moot:
                continue
            fact._nixed = True
            _run_all(fact._on_nix)
            to_nix.extend(fact._dependents)

    def on_nix[**P](
        self, callback: Callable[P, object], /, *args: P.args, **kwargs: P.kwargs
    ) -> Callable[[], None]:
        return self._register(self._nixed, self._on_nix, callback, args, kwargs)

    def on_moot[**P](
        self, callback: Callable[P, object], /, *args: P.args, **kwargs: P.kwargs
    ) -> Callable[[], None]:
        return self._register(self._moot, self._on_moot, callback, args, kwargs)

    def _register(
        self,
        occurred: bool,
        callbacks: list[_Callback],
        fn: Callable[..., object],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> _Callback:
        _check_not_background()
        callback = _as_callback(fn, args, kwargs)
        if occurred:
            callback()
        else:
            callbacks.append(callback)
        return callback

    @contextmanager
    def calculation(self) -> Iterator[None]:
        """Tracks what facts this fact's calculation depends on.

        If a fact calculation is already ongoing, a dependency will be added on this fact.

        The active fact is tracked via context variables. If a fact calculation exits,
        the context variable is marked dead; all tasks run to compute this fact MUST
        have returned before that happens. Any attempt to add a new dependency to this
        fact in such a task will raise an error.

        If the body depended on no nixable fact, the fact is constant: nothing
        records a dependency on it, and it never goes moot.
        """
        with self._calculation(is_report=False):
            yield

    @contextmanager
    def _calculation(self, *, is_report: bool) -> Iterator[None]:
        parent = _context.get()
        if isinstance(parent, _Marker):
            raise NixError(f"Cannot start a calculation in a {parent.value}")
        if self._calculated or self._nixed or self._moot:
            raise NixError("Fact cannot be calculated again")
        self._calculated = True
        in_report = is_report or (parent is not None and parent.in_report)
        frame = _Frame(self, in_report)
        token = _context.set(frame)
        try:
            yield
        finally:
            frame.alive = False
            _context.reset(token)
            if not self._dependencies and not is_report:
                self._make_constant()
            elif parent is not None:
                parent.add_dependency(self)

    def _make_constant(self) -> None:
        self._constant = True
        self._on_moot.clear()
        _graph.live.discard(self)

    def _make_moot(self) -> None:
        self._moot = True
        for fact in self._dependencies:
            fact._dependents.discard(self)
        for fact in self._dependents:
            fact._dependencies.discard(self)
        self._dependencies.clear()
        self._dependents.clear()
        _run_all(self._on_moot)


def _run_all(callbacks: list[_Callback]) -> None:
    to_call = callbacks[:]
    callbacks.clear()
    for callback in to_call:
        callback()


def run_background_task(coro: Coroutine[Any, Any, None]) -> None:
    """Start a background task to track external fact changes.

    Fact finders that return external facts (e.g. file contents, API query results)
    should start a background task to track when those facts are invalidated.

    Background tasks must not create new facts. They may nix existing facts, and
    they may update shared storage for subsequent fact calculation to use.
    Both of these must be done via `when_safe_to_nix`. Direct use of any nix API
    other than `when_safe_to_nix` in a background task will raise an error.

    When computing a one-shot report, this function will be a no-op.
    """
    _check_not_background()
    if _graph.task_group is None:
        coro.close()
        return
    context = copy_context()
    context.run(_context.set, _Marker.BACKGROUND)
    task = _graph.task_group.create_task(coro, context=context)
    _graph.background_tasks.add(task)
    task.add_done_callback(_graph.background_tasks.discard)


def when_safe_to_nix[**P](
    callback: Callable[P, object], /, *args: P.args, **kwargs: P.kwargs
) -> None:
    """Run *callback* once no active report calculation is in progress.

    Background tasks must not nix existing facts directly. Background tasks
    must not update shared storage directly. They must use this function to
    wait until it is safe.

    The callback may create facts, but must not start a calculation. An
    error will be raised if it tries. Facts created during a callback will
    not be marked moot until all recalculations triggered by callback nixes
    are done.
    """
    bound = _Callback(callback, args, kwargs)
    if _graph.calculating:
        _graph.pending.append(bound)
    else:
        _run_as_callback(bound)


def _run_as_callback(callback: _Callback) -> None:
    token = _context.set(_Marker.CALLBACK)
    try:
        callback()
    finally:
        _context.reset(token)


def _run_pending() -> None:
    while _graph.pending:
        _run_as_callback(_graph.pending.popleft())


def _sweep() -> None:
    reachable: set[Fact] = set()
    to_visit = [_graph.current_report] if _graph.current_report else []
    while to_visit:
        fact = to_visit.pop()
        if fact not in reachable:
            reachable.add(fact)
            to_visit.extend(fact._dependencies)
    moot = _graph.live - reachable
    _graph.live &= reachable
    for fact in moot:
        fact._make_moot()


@contextmanager
def session(task_group: asyncio.TaskGroup | None) -> Iterator[None]:
    """Hold the state of one watcher, or of one one-shot report.

    Background tasks are started in *task_group*, and cancelled on exit. All
    facts go moot on exit.
    """
    if _graph.active:
        raise NixError("A nix session is already active")
    _graph.active = True
    _graph.task_group = task_group
    try:
        yield
    finally:
        for task in _graph.background_tasks:
            task.cancel()
        _graph.task_group = None
        _graph.pending.clear()
        _graph.current_report = None
        _sweep()
        _graph.active = False


@contextmanager
def report_calculation() -> Iterator[Fact]:
    """Calculate a new report.

    On exit, the new report replaces the current report, and the callbacks
    queued by when_safe_to_nix run.
    """
    if _graph.calculating:
        raise NixError("A report calculation is already in progress")
    report = Fact()
    _graph.calculating = True
    try:
        with report._calculation(is_report=True):
            yield report
    finally:
        _graph.calculating = False
        _graph.current_report = report
        _run_pending()


def release_moot_facts() -> None:
    """Make moot each fact that the current report does not depend on.

    Does nothing unless the loop is idle: the current report must not be nixed,
    as the next report can then still use the facts of the current report.
    """
    report = _graph.current_report
    if not _graph.calculating and report is not None and not report.nixed:
        _sweep()
