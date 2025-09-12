"""Filesystem watching support for Mac OS X.

Leverages FSEvents to avoid polling. The same tracking logic is used to check
files for modifications as when polling, but triggered only when a filesystem
event occurs.
"""

import asyncio
from contextlib import ExitStack, contextmanager
from ctypes import (
    CFUNCTYPE,
    POINTER,
    addressof,
    c_double,
    c_int,
    c_size_t,
    c_uint32,
    c_uint64,
    c_void_p,
    cast,
)
from datetime import timedelta
from pathlib import Path
from typing import Callable, Collection, Iterator

from rubicon.objc import NSArray  # type: ignore[import-untyped]
from rubicon.objc.eventloop import RubiconEventLoop  # type: ignore[import-untyped]
from rubicon.objc.runtime import load_library  # type: ignore[import-untyped]

from .cohort import Cohort, on_add_cohort
from .tracking import nix_cohort_if_has_changes

libcf = load_library("CoreFoundation")
libcs = load_library("CoreServices")
libsys = load_library("System")  # GCD (libdispatch) symbols live in libSystem on macOS

# CFRunLoop
libcf.CFRunLoopGetCurrent.restype = c_void_p

# FSEvents APIs
libcs.FSEventsGetCurrentEventId.restype = c_uint64
libcs.FSEventStreamGetLatestEventId.argtypes = [
    c_void_p,  # ConstFSEventStreamRef
]
libcs.FSEventStreamGetLatestEventId.restype = c_uint64

libcs.FSEventStreamCreate.argtypes = [
    c_void_p,  # CFAllocatorRef,
    c_void_p,  # FSEventStreamCallback,
    c_void_p,  # void *context,
    c_void_p,  # CFArrayRef pathsToWatch,
    c_uint64,  # FSEventStreamEventId sinceWhen,
    c_double,  # CFTimeInterval latency,
    c_uint32,  # FSEventStreamCreateFlags flags
]
libcs.FSEventStreamCreate.restype = c_void_p

libcs.FSEventStreamSetDispatchQueue.argtypes = [
    c_void_p,  # FSEventStreamRef
    c_void_p,  # dispatch_queue_t
]
libcs.FSEventStreamSetDispatchQueue.restype = None

# FSEventStream start/shutdown functions: (FSEventStreamRef) -> Boolean
libcs.FSEventStreamStart.argtypes = [c_void_p]
libcs.FSEventStreamStart.restype = c_int
libcs.FSEventStreamStop.argtypes = [c_void_p]
libcs.FSEventStreamStop.restype = None
libcs.FSEventStreamInvalidate.argtypes = [c_void_p]
libcs.FSEventStreamInvalidate.restype = None
libcs.FSEventStreamRelease.argtypes = [c_void_p]
libcs.FSEventStreamRelease.restype = None


FSEventStreamCallback = CFUNCTYPE(
    None, c_void_p, c_void_p, c_size_t, c_void_p, c_void_p, c_void_p
)

K_FSEVENTSTREAM_CREATE_FLAG_USE_CF_TYPES = 0x00000001
"""Request CF types in callbacks.

The framework will invoke your callback function with CF types rather than raw C
types (i.e., a CFArrayRef of CFStringRefs, rather than a raw C array of raw C
string pointers).
"""

K_FSEVENTSTREAM_EVENT_FLAG_HISTORY_DONE = 0x00000010
"""End of historical events.

Denotes a sentinel event sent to mark the end of the "historical" events sent as
a result of specifying a sinceWhen value in the FSEventStreamCreate...() call
that created this event stream. (It will not be sent if
kFSEventStreamEventIdSinceNow was passed for sinceWhen.) After invoking the
client's callback with all the "historical" events that occurred before now, the
client's callback will be invoked with an event where the
kFSEventStreamEventFlagHistoryDone flag is set. The client should ignore the
path supplied in this callback.
"""

cohort_event_ids: dict[Cohort, int] = {}


def macosx_event_loop() -> asyncio.AbstractEventLoop:
    loop: asyncio.AbstractEventLoop = RubiconEventLoop()
    return loop


def add_cohort(cohort: Cohort) -> None:
    current_event_id = libcs.FSEventsGetCurrentEventId()
    cohort_event_ids[cohort] = current_event_id
    cohort.on_nix.append(lambda: cohort_event_ids.pop(cohort))


on_add_cohort.append(add_cohort)


def main_dispatch_queue() -> c_void_p:
    """Return the main dispatch queue.

    This uses a private data symbol exported by libdispatch.
    The function we are supposed to use to access it is declared as
    inline, so we cannot call it.
    """
    try:
        _dispatch_main_q_sym = c_void_p.in_dll(libsys, "_dispatch_main_q")
    except Exception:
        raise RuntimeError("_dispatch_main_q not found")

    return c_void_p(addressof(_dispatch_main_q_sym))


@contextmanager
def fs_event_stream(
    *,
    starting_event_id: int,
    directories: Collection[Path],
    callback: Callable[[], None],
    latency: timedelta,
) -> Iterator[c_void_p]:
    def convert_and_callback(
        stream_ref: c_void_p,
        client_info: c_void_p,
        num_events: int,
        event_paths: c_void_p,
        event_flags: c_void_p,
        event_ids: c_void_p,
    ) -> None:
        flags_ptr = cast(event_flags, POINTER(c_uint32))
        event_flag_ints = [int(flags_ptr[i]) for i in range(num_events)]
        if all(
            flag == K_FSEVENTSTREAM_EVENT_FLAG_HISTORY_DONE for flag in event_flag_ints
        ):
            return

        callback()

    c_callback = FSEventStreamCallback(convert_and_callback)

    event_stream: c_void_p = libcs.FSEventStreamCreate(
        None,
        c_callback,
        None,
        NSArray.arrayWithArray([str(dir) for dir in directories]),
        starting_event_id,
        c_double(latency.total_seconds()),
        K_FSEVENTSTREAM_CREATE_FLAG_USE_CF_TYPES,
    )

    libcs.FSEventStreamSetDispatchQueue(event_stream, main_dispatch_queue())

    if not libcs.FSEventStreamStart(event_stream):
        raise RuntimeError("Failed to start FS event stream")

    try:
        yield event_stream
    finally:
        libcs.FSEventStreamStop(event_stream)
        libcs.FSEventStreamInvalidate(event_stream)
        libcs.FSEventStreamRelease(event_stream)


@contextmanager
def await_changes_on_cohort(cohort: Cohort, latency: timedelta) -> Iterator[None]:
    event_id = cohort_event_ids[cohort]

    directories: set[Path] = set()
    for path in cohort.paths:
        # Assume all paths are files
        directories.add(path.parent)
    for glob in cohort.globs:
        directories.add(glob.base_path)

    with fs_event_stream(
        starting_event_id=event_id,
        directories=directories,
        callback=lambda: nix_cohort_if_has_changes(cohort),
        latency=latency,
    ) as event_stream:
        try:
            yield
        finally:
            if cohort in cohort_event_ids:
                # Resume the stream where we left off next time we await
                event_id = libcs.FSEventStreamGetLatestEventId(event_stream)
                cohort_event_ids[cohort] = event_id


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
    with ExitStack() as stack:
        for cohort in cohort_event_ids:
            stack.enter_context(await_changes_on_cohort(cohort, latency))
        await until.wait()
