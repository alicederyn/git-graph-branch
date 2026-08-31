import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from ..unit.git.utils import git_test_commit

CONTROL_C = b"\x03"
FIRST_FRAME_TIMEOUT = 10.0
EXIT_TIMEOUT = 5.0
WINDOW_SIZE = (40, 100)  # rows, columns

# Run the entry point in a fresh interpreter, as nix.install() patches Path and
# functools for every module imported after it, including prompt_toolkit's
# dependencies
ENTRYPOINT = [
    sys.executable,
    "-c",
    "import git_graph_branch.main; git_graph_branch.main.main()",
]


@contextmanager
def pty_child(
    args: Sequence[str], *, cwd: Path
) -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    """Run args with a pseudoterminal for stdin and stdout.

    Yields the process and the file descriptor for the other end of the
    terminal. Errors go to a pipe, so that a traceback is not interleaved with
    escape sequences.
    """
    terminal, child_terminal = pty.openpty()
    try:
        rows, columns = WINDOW_SIZE
        fcntl.ioctl(
            child_terminal, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )
        proc = subprocess.Popen(
            args,
            stdin=child_terminal,
            stdout=child_terminal,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=os.environ
            | {
                "PYTHONPATH": str(Path(__file__).parents[2]),
                "TERM": "xterm-256color",
                "COLUMNS": str(columns),
                "LINES": str(rows),
            },
        )
    finally:
        # The terminal only reports end of file once no writer is left
        os.close(child_terminal)
    try:
        with proc:
            try:
                yield proc, terminal
            finally:
                if proc.poll() is None:
                    proc.kill()
    finally:
        os.close(terminal)


def read_until(terminal: int, expected: bytes, deadline: float) -> bytes:
    """Read until expected is seen, the child exits, or the deadline passes."""
    received = b""
    while expected not in received:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if not select.select([terminal], [], [], remaining)[0]:
            break
        try:
            chunk = os.read(terminal, 65536)
        except OSError:
            break  # A closed terminal is reported as EIO, not end of file
        if not chunk:
            break
        received += chunk
    return received


@pytest.mark.parametrize("quit_key", [b"q", CONTROL_C])
def test_watch_mode_renders_then_quits(repo: Path, quit_key: bytes) -> None:
    git_test_commit()
    subprocess.check_call(["git", "branch", "sidequest"])

    with pty_child([*ENTRYPOINT, "--watch"], cwd=repo) as (proc, terminal):
        frame = read_until(
            terminal, b"sidequest", time.monotonic() + FIRST_FRAME_TIMEOUT
        )
        assert b"sidequest" in frame, (
            f"terminal: {frame.decode(errors='replace')!r}\n"
            f"errors: {proc.communicate()[1].decode(errors='replace')}"
        )

        os.write(terminal, quit_key)
        returncode = proc.wait(timeout=EXIT_TIMEOUT)
        assert proc.stderr is not None
        errors = proc.stderr.read().decode(errors="replace")

    assert errors == ""
    assert returncode == 0
