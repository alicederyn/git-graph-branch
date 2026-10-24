import asyncio
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from git_graph_branch import tmux
from git_graph_branch.tmux import track_visibility, wait_until_visible

FAKE_TMUX = dedent("""\
    import os
    import sys

    viewers = iter(os.environ["FAKE_TMUX_VIEWERS"].split(";"))
    notifications = os.environ["FAKE_TMUX_NOTIFICATIONS"].split(";")
    with open(os.environ["FAKE_TMUX_LOG"], "a") as log:
        log.write(" ".join(sys.argv[1:]) + "\\n")
        for line in sys.stdin:
            log.write(line)
            log.flush()
            print("%begin 1 1 0")
            if line.startswith("display-message"):
                print("viewers=" + next(viewers, ""))
            print("%end 1 1 0")
            if line.startswith("display-message"):
                print("\\n".join(notifications))
                notifications = []
            sys.stdout.flush()
""")


class RecordingEvent(asyncio.Event):
    def __init__(self) -> None:
        super().__init__()
        self.history: list[bool] = []

    def set(self) -> None:
        super().set()
        self.history.append(True)

    def clear(self) -> None:
        super().clear()
        self.history.append(False)


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "tmux"
    fake.write_text(f"#!{sys.executable}\n{FAKE_TMUX}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_TMUX_LOG", str(tmp_path / "log"))
    return tmp_path / "log"


async def test_queries_viewers_after_visibility_notifications(
    log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_TMUX_VIEWERS", "/dev/pts/0;")
    monkeypatch.setenv(
        "FAKE_TMUX_NOTIFICATIONS", "%window-add @6;%client-detached /dev/pts/0"
    )
    visible = RecordingEvent()

    task = asyncio.create_task(track_visibility("/tmp/socket", "%3", visible))
    for _ in range(100):
        if visible.history == [True, False]:
            break
        await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert visible.history == [True, False, True]
    commands = log.read_text().splitlines()
    assert commands[0].startswith("-S /tmp/socket -C new-session -s _git-graph-branch-")
    assert sum(c.startswith("display-message -p -t %3 ") for c in commands) == 2
    assert commands[-1].startswith("kill-session -t _git-graph-branch-")


async def test_wait_until_visible_returns_at_once_without_a_watch() -> None:
    await asyncio.wait_for(wait_until_visible(), timeout=1)


async def test_watch_outside_tmux_starts_no_tmux(log: Path) -> None:
    async with tmux.watch_window_visibility():
        await asyncio.wait_for(wait_until_visible(), timeout=1)

    assert not log.exists()
