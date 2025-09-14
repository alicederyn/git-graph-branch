"""Filesystem watching support for Linux.

Leverages inotify to avoid polling. The same tracking logic is used to check
files for modifications as when polling, but triggered only when a filesystem
event occurs.
"""

import asyncio
import ctypes
import ctypes.util
import os
from contextlib import contextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Collection, Generator

from .cohort import Cohort
from .patching import PATH_GLOB, is_dir
from .tracking import cohort_timestamps, nix_cohorts_with_changes


@contextmanager
def errno_check(path: Path | None = None) -> Generator[None, None, None]:
    ctypes.set_errno(0)
    try:
        yield
    finally:
        errno = ctypes.get_errno()
        if errno:
            err = OSError(errno, os.strerror(errno))
            if path:
                err.filename = str(path)
            raise err


libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

try:
    libc.inotify_init1.argtypes = [
        ctypes.c_int,  # fd
    ]
    libc.inotify_init1.restype = ctypes.c_int

    libc.inotify_add_watch.argtypes = [
        ctypes.c_int,  # fd
        ctypes.c_char_p,  # path
        ctypes.c_uint,  # mask
    ]
    libc.inotify_add_watch.restype = ctypes.c_int
except AttributeError:
    raise ImportError("inotify missing on this OS") from None


# Modify, move, create, delete, move self, delete self, overflow, unlink
WATCH_MASK = 0x4004FC2
READ_BYTES = 8192


async def await_data(event_loop: asyncio.AbstractEventLoop, fd: int) -> None:
    """Yields to the event loop until data is available on fd."""
    future = event_loop.create_future()
    event_loop.add_reader(fd, future.set_result, None)
    try:
        await future
    finally:
        event_loop.remove_reader(fd)


async def discard_all_data(
    event_loop: asyncio.AbstractEventLoop, fd: int, timeout: float
) -> None:
    """Discard all data on fd until the timeout is reached."""
    event_loop.add_reader(fd, os.read, fd, READ_BYTES)
    try:
        await asyncio.sleep(timeout)
    finally:
        event_loop.remove_reader(fd)


class DirectorySearch:
    def __init__(self) -> None:
        self.directories: set[Path] = set()
        self.checked: set[Path] = set()

    def add(self, path: Path) -> None:
        if path not in self.checked and is_dir(path):
            self.directories.add(path)
        self.checked.add(path)

    def add_parent(self, path: Path) -> None:
        candidate = path
        while candidate not in self.checked:
            self.checked.add(candidate)
            if is_dir(candidate):
                self.directories.add(candidate)
                return
            candidate = candidate.parent

    def add_cohort(self, cohort: Cohort) -> None:
        for path in cohort.paths:
            self.add_parent(path)
        for glob in cohort.globs:
            self.add_parent(glob.base_path)
            for f in PATH_GLOB(glob.base_path, "**/*"):
                self.add(f)


def directories_to_watch() -> set[Path]:
    search = DirectorySearch()
    for cohort in list(cohort_timestamps):
        search.add_cohort(cohort)
    return search.directories


def watch_all(fd: int, paths: Collection[Path]) -> None:
    for path in paths:
        bytepath = bytes(path)
        with errno_check(path):
            libc.inotify_add_watch(fd, bytepath, WATCH_MASK)


async def watch_for_changes(fd: int, latency: timedelta) -> None:
    event_loop = asyncio.get_running_loop()
    latency_seconds = latency.total_seconds()
    watched_directories: set[Path] = set()
    while True:
        directories = directories_to_watch()
        if directories != watched_directories:
            watch_all(fd, directories)
            watched_directories = directories
        else:
            # Only do a long-lived await if we haven't registered to watch
            # new directories
            await await_data(event_loop, fd)

        await discard_all_data(event_loop, fd, latency_seconds)
        nix_cohorts_with_changes()


async def await_changes_and_nix(
    until: asyncio.Event,
    *,
    latency: timedelta = timedelta(milliseconds=100),
) -> None:
    """Watch for any changes in watched files and nix any affected results.

    Parameters:
        until: Function will exit when this event is set.
        latency: How long to wait after hearing about an event from the kernel
            before checking watched files for changes. Specifying a larger value
            may result in more effective temporal coalescing, resulting in fewer
            callbacks and greater overall efficiency.
    """
    with errno_check():
        fd = libc.inotify_init1(os.O_NONBLOCK)
    try:
        task = asyncio.create_task(watch_for_changes(fd, latency))
        try:
            await until.wait()
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    finally:
        os.close(fd)
