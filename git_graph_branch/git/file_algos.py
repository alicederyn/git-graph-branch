import os
from pathlib import Path
from typing import Iterator


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
    """
    with open(file, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        chunks: list[bytes] = []
        while pos > 0:
            read_len = min(chunk_size, pos)
            pos -= read_len
            f.seek(pos)
            chunk = f.read(read_len)

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
