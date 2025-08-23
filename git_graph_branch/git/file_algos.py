import os
import time
from pathlib import Path
from threading import local
from types import TracebackType
from typing import Iterator, Protocol, Self, cast
from weakref import WeakKeyDictionary

MAX_FILE_HANDLES = 5
_localdata = local()


class Closeable(Protocol):
    def close(self) -> None: ...


class CloseablesCache:
    def __init__(self, *, max_size: int) -> None:
        self._closeables: WeakKeyDictionary[Closeable, float] = WeakKeyDictionary()
        self.max_size = max_size

    def add(self, closeable: Closeable) -> None:
        self._closeables[closeable] = time.monotonic()
        self._close_least_recently_used()

    def remove(self, closeable: Closeable) -> None:
        self._closeables.pop(closeable, None)

    def _close_least_recently_used(self) -> None:
        if len(self._closeables) <= self.max_size:
            return

        closeables = [(ts, c) for (c, ts) in self._closeables.items()]
        closeables.sort()
        for _, c in closeables[: -self.max_size]:
            c.close()
            del self._closeables[c]


def handle_cache() -> CloseablesCache:
    try:
        return cast("CloseablesCache", _localdata.handle_cache)
    except AttributeError:
        cache = _localdata.handle_cache = CloseablesCache(max_size=MAX_FILE_HANDLES)
        return cache


class PooledBinaryReader:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._loc = 0
        self._closed = False
        self._reopen()

    def _reopen(self) -> None:
        self._handle = self._path.open("rb")
        handle_cache().add(self._handle)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        handle_cache().remove(self._handle)
        self._handle.close()
        self._closed = True

    def read(self, size: int | None = -1, /) -> bytes:
        try:
            data = self._handle.read(size)
        except ValueError:
            if self._closed:
                raise
            self._reopen()
            self._handle.seek(self._loc, os.SEEK_SET)
            data = self._handle.read(size)
        self._loc += len(data)
        return data

    def seek(self, target: int, whence: int = os.SEEK_SET, /) -> int:
        try:
            self._loc = self._handle.seek(target, whence)
        except ValueError:
            if self._closed:
                raise
            self._reopen()
            if whence == os.SEEK_CUR:
                self._handle.seek(self._loc, os.SEEK_SET)
            self._loc = self._handle.seek(target, whence)
        return self._loc


def _byte_line_to_string(line: bytes) -> str:
    if line.endswith(b"\r\n"):
        return line[:-2].decode("utf-8") + "\n"
    if line.endswith(b"\r") or line.endswith(b"\n"):
        return line[:-1].decode("utf-8") + "\n"
    return line.decode("utf-8")


def readlines_reversed(file: Path, *, chunk_size: int = 1024) -> Iterator[str]:
    """Yield all lines in file, in reverse order.

    Equivalent to reversed(list(file.open("r", encoding="utf-8"))), but
    does not require loading the entire file into memory.

    If multiple iterators are opened simultaneously on a thread, at most five
    file handles will be held open at once.
    """
    with PooledBinaryReader(file) as f:
        pos = f.seek(0, os.SEEK_END)
        chunks: list[bytes] = []
        while pos > 0:
            read_len = min(chunk_size, pos)
            pos -= read_len
            f.seek(pos)
            chunk = f.read(read_len)

            # Close early if we can!
            if pos == 0:
                f.close()

            if chunks and (
                chunk.endswith(b"\n") or (chunk.endswith(b"\r") and chunks != [b"\n"])
            ):
                # Newline at chunk boundary
                yield _byte_line_to_string(b"".join(reversed(chunks)))
                chunks.clear()

            lines = chunk.splitlines(keepends=True)
            while len(lines) > 1:
                line = lines.pop()
                if chunks:
                    line = b"".join([line, *reversed(chunks)])
                    chunks.clear()
                yield _byte_line_to_string(line)

            if lines[0]:
                chunks.append(lines[0])

        if chunks:
            yield _byte_line_to_string(b"".join(reversed(chunks)))
