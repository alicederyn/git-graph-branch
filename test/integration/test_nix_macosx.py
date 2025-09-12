import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import AsyncGenerator, Callable, Coroutine, Iterator
from unittest.mock import Mock, patch

import pytest

from git_graph_branch.nix.cohort import Cohort, Glob

macosx = pytest.importorskip(
    "git_graph_branch.nix.macosx", reason="macOS-specific FSEvents module"
)
POSITIVE_TIMEOUT = 2.0
NEGATIVE_TIMEOUT = 0.25


def with_macosx_event_loop[**P](
    test: Callable[P, Coroutine[None, None, None]],
) -> Callable[P, None]:
    """Runs an async test within the Mac OS X Rubicon event loop.

    pytest-asyncio supports providing an event loop, but currently only via a
    policy, which have been deprecated in Python. Until the library is updated
    to match best practice, run the test in an event loop via a decorator.
    """

    @wraps(test)
    def run_test(*args: P.args, **kwargs: P.kwargs) -> None:
        asyncio.run(
            in_stack(test, *args, **kwargs), loop_factory=macosx.macosx_event_loop
        )

    return run_test


@pytest.fixture
def stack() -> AsyncExitStack:
    return AsyncExitStack()


async def in_stack[**P](
    fn: Callable[P, Coroutine[None, None, None]], *args: P.args, **kwargs: P.kwargs
) -> None:
    """Enters the first AsyncExitStack context manager in the arguments.

    Used to enter the stack fixture within the with_macosx_event_loop decorator.
    """
    stack = next(
        (a for a in (*args, *kwargs.values()) if isinstance(a, AsyncExitStack)),
        AsyncExitStack(),
    )
    async with stack:
        return await fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def cohort_event_ids() -> Iterator[dict[Cohort, int]]:
    with patch.dict(macosx.cohort_event_ids, clear=True) as d:
        yield d


@pytest.fixture(autouse=True)
def nix_cohort_if_has_changes() -> Iterator[Mock]:
    with patch.object(macosx, "nix_cohort_if_has_changes") as mock:
        yield mock


@pytest.fixture
def dir(tmp_path: Path) -> Path:
    path = tmp_path / "subdir"
    path.mkdir()
    return path


@pytest.fixture
def otherdir(tmp_path: Path) -> Path:
    path = tmp_path / "otherdir"
    path.mkdir()
    return path


async def flush_setup_events() -> None:
    """Ensure we don't get an event from the file creation."""
    await asyncio.sleep(0.1)


async def assert_called_async(fn: Mock) -> None:
    """Assert that fn is called, with a large timeout window to avoid flakes.

    Replaces the mock's side effect.
    """
    called = asyncio.Event()
    fn.side_effect = lambda *_args, **_kwargs: called.set()
    try:
        await asyncio.wait_for(called.wait(), POSITIVE_TIMEOUT)
    except TimeoutError:
        pass
    fn.side_effect = None
    fn.assert_called()


@asynccontextmanager
async def await_changes_and_nix_task(
    cohort: Cohort,
) -> AsyncGenerator[asyncio.Task[None], None]:
    await flush_setup_events()
    until = asyncio.Event()
    macosx.add_cohort(cohort)
    task = asyncio.create_task(macosx.await_changes_and_nix(until))
    try:
        yield task
    finally:
        until.set()
        await task


@with_macosx_event_loop
async def test_path_no_changes(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    await asyncio.sleep(NEGATIVE_TIMEOUT)

    # THEN
    nix_cohort_if_has_changes.assert_not_called()


@with_macosx_event_loop
async def test_path_touched(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    watched.write_text("updated")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_path_created(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    watched.write_text("created")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_path_deleted(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    watched.unlink()

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_dir_deletion_race(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN we capture the event ID early
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})
    await flush_setup_events()
    macosx.add_cohort(cohort)

    # AND the underlying directory is deleted
    watched.unlink()
    dir.rmdir()
    await flush_setup_events()

    # WHEN we register for events
    until = asyncio.Event()
    task = asyncio.create_task(macosx.await_changes_and_nix(until))
    stack.push_async_callback(lambda: task)
    stack.callback(until.set)

    # THEN the nix logic is still called
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_path_two_changes(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    watched.write_text("updated")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)

    # GIVEN
    nix_cohort_if_has_changes.reset_mock()

    # WHEN
    watched.write_text("updated again")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_path_change_in_different_dir(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
    otherdir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    unwatched = otherdir / "unwatched.txt"
    watched.write_text("init")
    unwatched.write_text("init")
    cohort = Cohort(paths={watched})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    unwatched.write_text("updated")
    await asyncio.sleep(NEGATIVE_TIMEOUT)

    # THEN
    nix_cohort_if_has_changes.assert_not_called()


@with_macosx_event_loop
async def test_multiple_events_coalesced(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    f1 = dir / "watched.txt"
    f2 = dir / "other.txt"
    f1.write_text("file1")
    f2.write_text("file2")
    cohort = Cohort(paths={f1})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    f1.write_text("updated")
    f2.write_text("updated")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_once()


@with_macosx_event_loop
async def test_glob_touched(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(globs={Glob(base_path=dir, pattern="*.txt", case_sensitive=None)})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    watched.write_text("updated")

    # THEN
    await assert_called_async(nix_cohort_if_has_changes)
    nix_cohort_if_has_changes.assert_called_with(cohort)


@with_macosx_event_loop
async def test_glob_change_in_different_dir(
    nix_cohort_if_has_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
    otherdir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    unwatched = otherdir / "unwatched.txt"
    watched.write_text("init")
    unwatched.write_text("init")
    cohort = Cohort(globs={Glob(base_path=dir, pattern="*.txt", case_sensitive=None)})
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # WHEN
    unwatched.write_text("updated")
    await asyncio.sleep(NEGATIVE_TIMEOUT)

    # THEN
    nix_cohort_if_has_changes.assert_not_called()
