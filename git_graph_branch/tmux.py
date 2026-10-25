"""Track whether a tmux client shows the window of this process's pane (ADR 6).

A tmux control-mode client, attached to a session of its own, gets notifications
for every session. After each one that can change which window a client shows,
it queries the clients that show this pane's window.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress

VIEWERS_FORMAT = "viewers=#{window_active_clients_list}"
VISIBILITY_NOTIFICATIONS = (
    "%session-window-changed ",
    "%client-detached ",
    "%client-session-changed ",
)
IDLE_COMMAND = "sleep 2147483647"

_visible: asyncio.Event | None = None


async def wait_until_visible() -> None:
    """Return once the window is visible, or at once if no watch is running."""
    if _visible is not None:
        await _visible.wait()


@asynccontextmanager
async def watch_window_visibility(
    on_hide: Callable[[], None] = lambda: None,
) -> AsyncIterator[None]:
    """Track the visibility of this pane's window while the body runs, and call
    on_hide when a query finds it hidden.

    Outside tmux, or if tmux fails, the window counts as visible.
    """
    global _visible
    tmux_env = os.environ.get("TMUX")
    pane = os.environ.get("TMUX_PANE")
    if not tmux_env or not pane:
        yield
        return
    visible = asyncio.Event()
    visible.set()
    _visible = visible
    try:
        async with asyncio.TaskGroup() as task_group:
            task = task_group.create_task(
                track_visibility(tmux_env.split(",")[0], pane, visible, on_hide)
            )
            try:
                yield
            finally:
                task.cancel()
    finally:
        _visible = None


def parse_viewers(line: str) -> bool | None:
    """Whether a query reply line shows any viewers, or None for another line."""
    if not line.startswith("viewers="):
        return None
    return bool(line.removeprefix("viewers="))


async def track_visibility(
    socket: str,
    pane: str,
    visible: asyncio.Event,
    on_hide: Callable[[], None] = lambda: None,
) -> None:
    session = f"_git-graph-branch-{os.getpid()}"
    env = {name: value for name, value in os.environ.items() if name != "TMUX"}
    try:
        process = await asyncio.create_subprocess_exec(
            *("tmux", "-S", socket, "-C", "new-session", "-s", session, IDLE_COMMAND),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
    except OSError:
        return
    assert process.stdin and process.stdout
    stdin = process.stdin
    query = f"display-message -p -t {pane} '{VIEWERS_FORMAT}'\n".encode()
    stdin.write(f"set-option -t {session} destroy-unattached on\n".encode() + query)
    try:
        in_block = False
        async for raw_line in process.stdout:
            line = raw_line.decode(errors="replace").rstrip("\n")
            if line.startswith("%begin "):
                in_block = True
            elif line.startswith(("%end ", "%error ")):
                in_block = False
            elif in_block:
                viewers = parse_viewers(line)
                if viewers is True:
                    visible.set()
                elif viewers is False:
                    visible.clear()
                    on_hide()
            elif line.startswith(VISIBILITY_NOTIFICATIONS):
                stdin.write(query)
    finally:
        visible.set()
        with suppress(OSError):
            stdin.write(f"kill-session -t {session}\n".encode())
            stdin.close()
        with suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=1)
        if process.returncode is None:
            process.terminate()
