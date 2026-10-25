import pytest

from git_graph_branch.display import Config, Frame
from git_graph_branch.links import Link
from git_graph_branch.ui import ShowFrame, show_once

OPEN = "\x1b]8;;https://x\x1b\\"
CLOSE = "\x1b]8;;\x1b\\"


async def show_linked_icon(show: ShowFrame) -> None:
    show(Frame([[("", "branch "), ("", "👍", Link("https://x"))]], None))


async def test_links_are_hyperlinks_with_color(
    capsys: pytest.CaptureFixture[str],
) -> None:
    await show_once(Config(color=True), show_linked_icon)

    out = capsys.readouterr().out
    assert out.index(OPEN) < out.index("👍") < out.index(CLOSE)


async def test_links_are_plain_text_without_color(
    capsys: pytest.CaptureFixture[str],
) -> None:
    await show_once(Config(color=False), show_linked_icon)

    assert capsys.readouterr().out == "branch 👍\r\n"
