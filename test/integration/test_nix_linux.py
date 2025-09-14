import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncGenerator, Iterator
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio

from git_graph_branch.nix.cohort import Cohort, Glob

from .utils import NEGATIVE_TIMEOUT, assert_called_async, flush_setup_events

linux = pytest.importorskip(
    "git_graph_branch.nix.linux",
    reason="Linux-specific inotify module",
    exc_type=ImportError,
)


@pytest.fixture(autouse=True)
def cohort_event_ids() -> Iterator[dict[Cohort, int]]:
    with patch.dict(linux.cohort_timestamps, clear=True) as d:
        yield d


@pytest.fixture(autouse=True)
def nix_cohorts_with_changes() -> Iterator[Mock]:
    with patch.object(linux, "nix_cohorts_with_changes") as mock:
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


@pytest_asyncio.fixture
async def stack() -> AsyncGenerator[AsyncExitStack, None]:
    async with AsyncExitStack() as exit_stack:
        yield exit_stack


@asynccontextmanager
async def await_changes_and_nix_task(
    cohort: Cohort,
    *,
    absorb_first_nix: bool = True,
    latency: timedelta = timedelta(milliseconds=100),
) -> AsyncGenerator[asyncio.Task[None], None]:
    await flush_setup_events()
    until = asyncio.Event()
    linux.cohort_timestamps[cohort] = -1
    task = asyncio.create_task(linux.await_changes_and_nix(until, latency=latency))
    if absorb_first_nix:
        await assert_called_async(linux.nix_cohorts_with_changes)
        linux.nix_cohorts_with_changes.reset_mock()
    try:
        yield task
    finally:
        until.set()
        await task


async def test_immediate_check_for_changes(
    nix_cohorts_with_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    watched = dir / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(paths={watched})

    # WHEN
    await stack.enter_async_context(
        await_changes_and_nix_task(cohort, absorb_first_nix=False)
    )

    # THEN
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.assert_called()


async def test_path_no_changes(
    nix_cohorts_with_changes: Mock,
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
    nix_cohorts_with_changes.assert_not_called()


async def test_path_touched(
    nix_cohorts_with_changes: Mock,
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
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.assert_called()


async def test_path_change_in_different_dir(
    nix_cohorts_with_changes: Mock,
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
    nix_cohorts_with_changes.assert_not_called()


async def test_multiple_events_coalesced(
    nix_cohorts_with_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN
    f1 = dir / "watched.txt"
    f2 = dir / "other.txt"
    f1.write_text("file1")
    f2.write_text("file2")
    cohort = Cohort(paths={f1})
    await stack.enter_async_context(
        await_changes_and_nix_task(cohort, latency=timedelta(seconds=0.2))
    )

    # WHEN
    f1.write_text("updated")
    f2.write_text("updated")
    await asyncio.sleep(0.1)
    f1.write_text("updated")

    # THEN
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.assert_called_once()


async def test_glob_touched(
    nix_cohorts_with_changes: Mock,
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
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.assert_called()


async def test_glob_change_in_different_dir(
    nix_cohorts_with_changes: Mock,
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
    nix_cohorts_with_changes.assert_not_called()


async def test_rglob_new_subdir(
    nix_cohorts_with_changes: Mock,
    stack: AsyncExitStack,
    dir: Path,
) -> None:
    # GIVEN a recursive glob is watched
    (dir / "foo").mkdir()
    watched = dir / "foo" / "watched.txt"
    watched.write_text("init")
    cohort = Cohort(
        globs={Glob(base_path=dir, pattern="**/*.txt", case_sensitive=None)}
    )
    await stack.enter_async_context(await_changes_and_nix_task(cohort))

    # AND a new directory is created and the related event observed
    (dir / "bar").mkdir()
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.reset_mock()

    # AND the callback is hit again (in case of a race)
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.reset_mock()

    # BUT not a third time
    await asyncio.sleep(NEGATIVE_TIMEOUT)
    nix_cohorts_with_changes.assert_not_called()

    # WHEN a new file is created in the new subdirectory
    (dir / "bar" / "another.txt").write_text("init")

    # THEN the second event is also spotted
    await assert_called_async(nix_cohorts_with_changes)
    nix_cohorts_with_changes.assert_called()
