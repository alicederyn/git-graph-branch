from asyncio import AbstractEventLoop
from contextlib import contextmanager
from time import sleep
from typing import Any, Iterator
from unittest.mock import Mock, patch

from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingEmitter
from watchdog.utils import BaseThread

from ._tracker import _trackers


class _FakeThread(BaseThread):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pretend_to_be_running = False
        super().__init__(*args, **kwargs)  # type: ignore

    def start(self) -> None:
        self._pretend_to_be_running = True
        self.on_thread_start()  # type: ignore

    def stop(self) -> None:
        self.on_thread_stop()  # type: ignore
        self._pretend_to_be_running = False

    def join(self, timeout: float | None = None) -> None:
        pass

    def is_alive(self) -> bool:
        return self._pretend_to_be_running


class _ManualEmitter(_FakeThread, PollingEmitter):
    def on_thread_start(self) -> None:
        super().on_thread_start()  # type: ignore
        sleep(0.01)  # Ensure timestamps change between snapshots


class ManualObserver(_FakeThread, BaseObserver):
    def __init__(self) -> None:
        super().__init__(emitter_class=_ManualEmitter, timeout=0)

    def check_for_changes(self) -> None:
        for emitter in self.emitters:
            emitter.queue_events(timeout=0)
        sleep(0.01)  # Ensure timestamps change between snapshots
        while not self.event_queue.empty():
            self.dispatch_events(self.event_queue)  # type: ignore


class FakeNixer:
    def __init__(self) -> None:
        self.is_active = True
        self.is_nixed = False

    def nix(self) -> None:
        self.is_nixed = True
        self.is_active = False


@contextmanager
def patch_manual_observer() -> Iterator[ManualObserver]:
    """Patch ixnay to allow manual triggering of file watching."""
    _trackers.cache_clear()
    with patch("git_graph_branch.ixnay._tracker.Observer") as observer_factory, patch(
        "git_graph_branch.ixnay._tracker.get_running_loop"
    ) as get_running_loop:
        observer = ManualObserver()
        observer_factory.return_value = observer
        event_loop = Mock(AbstractEventLoop)
        event_loop.call_soon_threadsafe.side_effect = lambda callable: callable()
        get_running_loop.return_value = event_loop
        try:
            yield observer
        finally:
            if _trackers.cache_info().currsize == 1:
                _trackers()._stop()
                _trackers.cache_clear()
