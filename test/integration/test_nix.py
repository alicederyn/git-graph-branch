import asyncio
import functools
import os
from collections.abc import AsyncGenerator, Iterator
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio

from git_graph_branch import nix

CONFIG = ".gitconfig"
PACK_DIR = ".git/objects/pack"
PACK1 = f"{PACK_DIR}/1.pack"
PACK2 = f"{PACK_DIR}/2.pack"


def write_to(path: Path, content: str, at: datetime | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    mtime = at or datetime.now(UTC)
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))


@pytest.fixture(autouse=True)
def fake_repo(tmp_path: Path) -> Iterator[None]:
    mtime = datetime.now(UTC) - timedelta(minutes=1)

    orig_wd = os.getcwd()
    os.chdir(tmp_path)

    # Create some files, with modification timestamp
    # a minute in the past
    for path in (CONFIG, PACK1, PACK2):
        write_to(Path(path), "init", mtime)

    yield None

    os.chdir(orig_wd)


@pytest.fixture(autouse=True)
def restore_functools() -> Iterator[None]:
    """Restore functools functions patched by nix when tests finish."""
    original_lru_cache = functools.lru_cache
    yield None
    functools.lru_cache = original_lru_cache


@pytest.fixture(autouse=True)
def nix_path() -> Iterator[Any]:
    """Prevent nix actually patching Path."""

    class FakePath:
        def __init__(self, path: str | Path) -> None:
            self._path = Path(path)

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, FakePath):
                return False
            return self._path == other._path

        def __hash__(self) -> int:
            return hash(self._path)

        def __lt__(self, other: Any) -> bool:
            if not isinstance(other, FakePath):
                return NotImplemented
            return self._path < other._path

        def __repr__(self) -> str:
            return f"FakePath({str(self._path)!r})"

        def exists(self) -> bool:
            try:
                self.stat()
                return True
            except FileNotFoundError:
                return False

        def is_dir(self) -> bool:
            raise NotImplementedError()

        def is_file(self) -> bool:
            raise NotImplementedError()

        def open(self) -> Any:
            raise NotImplementedError()

        def read_bytes(self) -> bytes:
            raise NotImplementedError()

        def read_text(self) -> str:
            return self._path.read_text()

        def stat(self) -> Any:
            return self._path.stat()

        def write_bytes(self, data: Any) -> None:
            raise NotImplementedError()

        def write_text(self, data: str) -> None:
            raise NotImplementedError()

        def glob(self, pattern: str, **kwargs: Any) -> "Iterator[FakePath]":
            for p in self._path.glob(pattern, **kwargs):
                yield FakePath(str(p))

        def __str__(self) -> str:
            return str(self._path)

    with (
        patch.object(nix.patching, "Path", FakePath),
        patch.object(nix.patching, "PATH_STAT", FakePath.stat),
        patch.object(nix.tracking, "PATH_STAT", FakePath.stat),
    ):
        yield FakePath


@pytest_asyncio.fixture()
async def stack() -> AsyncGenerator[AsyncExitStack, None]:
    async with AsyncExitStack() as stack:
        yield stack


@patch.object(nix.loop, "efficient_await_and_nix_impl", lambda: None)
async def test_polling_invalidation_loop(nix_path: Any, stack: AsyncExitStack) -> None:
    queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    async def nix_logic() -> None:
        nix.install()

        @functools.cache
        def pack_files() -> list[Path]:
            return list(nix_path(PACK_DIR).glob("*.pack"))

        async with nix.watcher(poll_every=timedelta(milliseconds=5)) as needs_refresh:
            while await needs_refresh():
                files: dict[str, str] = {CONFIG: nix_path(CONFIG).read_text()}
                assert not nix_path("nonexistent.txt").exists()
                for pack_file in pack_files():
                    files[str(pack_file)] = pack_file.read_text()
                await queue.put(files)

    tg = await stack.enter_async_context(asyncio.TaskGroup())
    nix_task = tg.create_task(nix_logic())
    stack.callback(nix_task.cancel)

    # Logic executes once immediately
    files = await asyncio.wait_for(queue.get(), timeout=1)
    assert files == {
        CONFIG: "init",
        PACK1: "init",
        PACK2: "init",
    }

    # Logic sleeps while no file changes detected
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)

    # Add another pack file
    pack3 = f"{PACK_DIR}/3.pack"
    write_to(Path(pack3), "init", datetime.now(UTC))

    # Logic executes again
    files = await asyncio.wait_for(queue.get(), timeout=1)
    assert files == {
        CONFIG: "init",
        PACK1: "init",
        PACK2: "init",
        pack3: "init",
    }
