from __future__ import annotations

from asyncio import get_running_loop
from collections import defaultdict
from functools import cache
from itertools import chain
from pathlib import Path
from typing import Iterator
from weakref import WeakKeyDictionary, ref

from watchdog.events import (
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MODIFIED,
    FileSystemEvent,
    FileSystemMovedEvent,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from ._nixer import Nixer

FILESET_CHANGE_EVENT_TYPES = frozenset(
    [EVENT_TYPE_CREATED, EVENT_TYPE_DELETED, EVENT_TYPE_MODIFIED]
)


def parents(*paths: Path | None) -> Iterator[Path]:
    seen = set[Path]()
    for parent in (p.parent for p in paths if p):
        while parent and parent not in seen:
            yield parent
            seen.add(parent)
            parent = parent.parent


class Trackers:
    """Asyncio adapter around Observer.

    Methods must be
     - threadsafe, as watchdog issues callbacks off the event loop thread
     - non-blocking, as weakref issues callbacks mid-execution
    """

    def __init__(self) -> None:
        self.watching: set[Path] = set()
        self.trackers: WeakKeyDictionary[Nixer, ref[Nixer]] = WeakKeyDictionary()
        self.nixer_by_path: dict[Path, set[ref[Nixer]]] = defaultdict(set)
        self.path_by_nixer: dict[ref[Nixer], set[Path]] = defaultdict(set)
        self.event_loop = get_running_loop()
        self.todo: set[ref[Nixer]] = set()
        self.coro_scheduled = False

        self.observer: BaseObserver = Observer()
        self.observer.daemon = True
        self.observer.start()  # type: ignore

    def __del__(self) -> None:
        self._stop()

    def _stop(self) -> None:
        if self.observer.is_alive():
            self.observer.unschedule_all()  # type: ignore
            self.observer.stop()  # type: ignore
            self.observer.join()
            for nixer_ref in chain(self.path_by_nixer.keys(), self.todo):
                nixer = nixer_ref()
                if nixer is not None:
                    nixer.nix()

    def register_path(self, path: Path) -> None:
        try:
            if path not in self.watching:
                self.watching.add(path)
                self.observer.schedule(self, path, recursive=True)  # type: ignore
        except FileNotFoundError:
            self.register_path(path.parent)

    def watch_path(self, path: Path, nixer: Nixer) -> None:
        """If path updates, schedule nix on the event loop.

        Retains only a weak reference to nixer.
        """
        try:
            tracker = self.trackers[nixer]
        except KeyError:
            tracker = ref(nixer, self.remove_reference)
            self.trackers[nixer] = tracker

        self.nixer_by_path[path].add(tracker)
        self.path_by_nixer[tracker].add(path)

    def remove_reference(self, tracker: ref[Nixer]) -> None:
        """Remove expired weak nixer reference.

        May interrupt other thread execution.
        """
        paths = self.path_by_nixer[tracker]
        del self.path_by_nixer[tracker]
        for path in paths:
            self.nixer_by_path[path].discard(tracker)

    def dispatch(self, event: FileSystemEvent) -> None:
        src_path = Path(event.src_path)
        self.notify_for_path(src_path)
        dest_path = (
            Path(event.dest_path) if isinstance(event, FileSystemMovedEvent) else None
        )
        if dest_path:
            self.notify_for_path(dest_path)
        if event.event_type in FILESET_CHANGE_EVENT_TYPES:
            for parent in parents(src_path, dest_path):
                self.notify_for_path(parent)

    def notify_for_path(self, path: Path) -> None:
        nixers = list(self.nixer_by_path.get(path, []))
        for nixer in nixers:
            watched_paths = self.path_by_nixer.pop(nixer, None)
            if watched_paths is not None:
                self.schedule_nixer(nixer)
                for watched_path in watched_paths:
                    self.nixer_by_path[watched_path].discard(nixer)

    def schedule_nixer(self, nixer: ref[Nixer]) -> None:
        # Thread-safety note: Order of these four lines is important
        self.todo.add(nixer)  # FIRST access todo
        if not self.coro_scheduled:  # THEN access coro_scheduled
            self.coro_scheduled = True
            # FINALLY, schedule nix
            self.event_loop.call_soon_threadsafe(self.nix)

    def nix(self) -> None:
        # Thread-safety note: Order of these two lines is important
        self.coro_scheduled = False  # FIRST update coro_scheduled
        todo = list(self.todo)  # THEN access todo

        while todo:
            nixer_ref = todo.pop()
            self.todo.discard(nixer_ref)
            nixer = nixer_ref()
            if nixer:
                nixer.nix()


@cache
def _trackers() -> Trackers:
    return Trackers()


def watch_path(path: Path, nixer: Nixer, *, root_path: Path | None = None) -> None:
    """Invalidate nixer on the event loop if path changes.

    Nixer is only guaranteed to be invalidated once, no matter how many times
    it is registered. Deduplication is based on nixer identity, not
    equality. At-most-once execution is not guaranteed.

    If root_path is supplied, it will be registered for change watching instead of
    path. This allows costs to be amortized across multiple calls, as it is
    cheaper to watch a single directory recursively, and there are limits to how
    many locations can be watched.
    """
    if nixer.is_active:
        _trackers().register_path(root_path or path)
        _trackers().watch_path(path, nixer)
