import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from ..unit.git.utils import git_test_commit

CONTROL_C = b"\x03"
WHEEL_UP = b"\x1b[<64;1;1M"  # SGR mouse report, button 64, at the top left
PAGE_DOWN = b"\x1b[6~"
FIRST_FRAME_TIMEOUT = 10.0
REDRAW_TIMEOUT = 5.0
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
    args: Sequence[str],
    *,
    cwd: Path,
    window_size: tuple[int, int] = WINDOW_SIZE,
    env: Mapping[str, str] = {},
) -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    """Run args with a pseudoterminal for stdin and stdout.

    Yields the process and the file descriptor for the other end of the
    terminal. Errors go to a pipe, so that a traceback is not interleaved with
    escape sequences.
    """
    terminal, child_terminal = pty.openpty()
    try:
        rows, columns = window_size
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
            }
            | dict(env),
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


def describe(received: bytes, proc: subprocess.Popen[bytes]) -> str:
    """Report the terminal and the child's errors, for a failed assertion.

    The child is killed first, as watch mode never exits on its own and its
    errors are only readable up to end of file.
    """
    proc.kill()
    errors = proc.communicate(timeout=EXIT_TIMEOUT)[1].decode(errors="replace")
    return f"terminal: {received.decode(errors='replace')!r}\nerrors: {errors}"


def test_the_wheel_and_page_keys_move_the_window(repo: Path) -> None:
    git_test_commit()
    # No two names share a character, so a redraw that changes a row writes the
    # whole name. Rows sort by name, descending, with main last.
    for letter in "abcdefghijklmnopqrs":
        subprocess.check_call(["git", "branch", letter * 3])
    rows, columns = 6, 100

    with pty_child([*ENTRYPOINT, "--watch"], cwd=repo, window_size=(rows, columns)) as (
        proc,
        terminal,
    ):
        # The window centres on main, which is the last of the twenty rows
        frame = read_until(terminal, b"main", time.monotonic() + FIRST_FRAME_TIMEOUT)
        assert b"main" in frame, describe(frame, proc)
        assert b"sss" not in frame, describe(frame, proc)

        os.write(terminal, WHEEL_UP * 20)
        top = read_until(terminal, b"nnn", time.monotonic() + REDRAW_TIMEOUT)
        assert b"sss" in top, describe(top, proc)

        os.write(terminal, PAGE_DOWN)
        paged = read_until(terminal, b"hhh", time.monotonic() + REDRAW_TIMEOUT)
        assert b"mmm" in paged, describe(paged, proc)
        assert b"hhh" in paged, describe(paged, proc)
        assert b"nnn" not in paged, describe(paged, proc)

        os.write(terminal, b"q")
        assert proc.wait(timeout=EXIT_TIMEOUT) == 0


@pytest.mark.parametrize("quit_key", [b"q", CONTROL_C])
def test_watch_mode_renders_then_quits(repo: Path, quit_key: bytes) -> None:
    git_test_commit()
    subprocess.check_call(["git", "branch", "sidequest"])

    with pty_child([*ENTRYPOINT, "--watch"], cwd=repo) as (proc, terminal):
        frame = read_until(
            terminal, b"sidequest", time.monotonic() + FIRST_FRAME_TIMEOUT
        )
        assert b"sidequest" in frame, describe(frame, proc)

        os.write(terminal, quit_key)
        returncode = proc.wait(timeout=EXIT_TIMEOUT)
        assert proc.stderr is not None
        errors = proc.stderr.read().decode(errors="replace")

    assert errors == ""
    assert returncode == 0


@pytest.mark.parametrize("variable, value", [("TERM", "dumb"), ("NO_COLOR", "1")])
def test_watch_mode_color_flag_overrides_environment(
    repo: Path, variable: str, value: str
) -> None:
    git_test_commit()
    coloured_head = b"\x1b[0;35;1mmain"

    with pty_child(
        [*ENTRYPOINT, "--watch", "--color"], cwd=repo, env={variable: value}
    ) as (proc, terminal):
        frame = read_until(
            terminal, coloured_head, time.monotonic() + FIRST_FRAME_TIMEOUT
        )
        assert coloured_head in frame, describe(frame, proc)

        os.write(terminal, b"q")
        proc.wait(timeout=EXIT_TIMEOUT)
