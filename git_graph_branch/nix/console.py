from contextlib import contextmanager
from io import StringIO
from types import TracebackType
from typing import Any, BinaryIO, Generator, Iterable, Self, TextIO


class NixableIO(TextIO):
    def __init__(self, underlying: TextIO, *, hold_io: bool = False) -> None:
        self._active = self._underlying = underlying
        self._buffer: StringIO | None = None
        if hold_io:
            self.hold_io()

    def flush_to_underlying(self) -> None:
        if self._buffer:
            self._underlying.write(self._buffer.getvalue())
            self._underlying.flush()
            self._active = self._underlying
            self._buffer = None

    def hold_io(self) -> None:
        self._underlying.flush()
        self._active = self._buffer = StringIO()

    @property
    def mode(self) -> str:
        return self._active.mode

    @property
    def name(self) -> str:
        return self._active.name

    def close(self) -> None:
        raise RuntimeError("Cannot close a nixable console object")

    @property
    def closed(self) -> bool:
        return self._active.closed

    def fileno(self) -> int:
        return self._active.fileno()

    def flush(self) -> None:
        self._active.flush()

    def isatty(self) -> bool:
        return self._active.isatty()

    def read(self, n: int = -1, /) -> str:
        return self._active.read(n)

    def readable(self) -> bool:
        return self._active.readable()

    def readline(self, limit: int = -1, /) -> str:
        return self._active.readline(limit)

    def readlines(self, hint: int = -1, /) -> list[str]:
        return self._active.readlines(hint)

    def seek(self, offset: int, whence: int = 0, /) -> int:
        return self._active.seek(offset, whence)

    def seekable(self) -> bool:
        return self._active.seekable()

    def tell(self) -> int:
        return self._active.tell()

    def truncate(self, size: int | None = None, /) -> int:
        return self._active.truncate(size)

    def writable(self) -> bool:
        return self._active.writable()

    def write(self, s: str, /) -> int:
        return self._active.write(s)

    def writelines(self, lines: Iterable[str], /) -> None:
        self._active.writelines(lines)

    @property
    def buffer(self) -> BinaryIO:
        return self._active.buffer

    @property
    def encoding(self) -> str:
        return self._active.encoding

    @property
    def errors(self) -> str | None:
        return self._active.errors

    @property
    def line_buffering(self) -> int:
        return self._active.line_buffering

    @property
    def newlines(self) -> Any:
        return self._active.newlines

    def __enter__(self) -> Self:
        self._active.__enter__()
        return self

    def __exit__(
        self,
        type_: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._active.__exit__(type_, value, None)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> str:
        return next(self._active)


_nixable_stdout: NixableIO | None = None
_nixable_stderr: NixableIO | None = None


def flush_and_hold_io() -> None:
    if _nixable_stdout is None or _nixable_stderr is None:
        raise RuntimeError("nix not installed")

    _nixable_stdout.flush_to_underlying()
    _nixable_stdout.hold_io()
    _nixable_stderr.flush_to_underlying()
    _nixable_stderr.hold_io()


@contextmanager
def flush_io_on_shutdown() -> Generator[None, None, None]:
    if _nixable_stdout is None or _nixable_stderr is None:
        raise RuntimeError("nix not installed")

    try:
        yield
    finally:
        _nixable_stdout.flush_to_underlying()
        _nixable_stderr.flush_to_underlying()
