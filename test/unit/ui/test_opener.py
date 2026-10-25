import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.formatted_text import StyleAndTextTuples

from git_graph_branch.links import MOONS, Icon, Opener


@pytest.fixture(autouse=True)
def MOON_SECONDS() -> Iterator[None]:
    with patch("git_graph_branch.links.MOON_SECONDS", 0.001):
        yield


@pytest.fixture(autouse=True)
def open_command() -> Iterator[MagicMock]:
    with patch(
        "git_graph_branch.links.open_command", return_value=["open", "%s"]
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def run_open_command() -> Iterator[AsyncMock]:
    with patch("git_graph_branch.links.run_open_command") as mock:
        yield mock


@pytest.fixture(autouse=True)
def open_in_background() -> Iterator[MagicMock]:
    with patch("git_graph_branch.links.open_in_background") as mock:
        yield mock


async def finish(opener: Opener) -> None:
    await asyncio.gather(*opener.tasks)


def texts(row: StyleAndTextTuples) -> list[str]:
    return [fragment[1] for fragment in row]


async def test_a_click_opens_the_link(run_open_command: AsyncMock) -> None:
    opener = Opener(MagicMock())

    opener.click("https://x")
    await finish(opener)

    run_open_command.assert_awaited_once_with(["open", "%s"], "https://x")


async def test_a_link_without_a_command_is_opened_by_webbrowser(
    open_command: MagicMock, open_in_background: MagicMock
) -> None:
    open_command.return_value = None
    opener = Opener(MagicMock())

    opener.click("https://x")
    await finish(opener)

    open_in_background.assert_called_once_with("https://x")


async def test_a_second_click_while_opening_is_ignored(
    run_open_command: AsyncMock,
) -> None:
    opener = Opener(MagicMock())

    opener.click("https://x")
    opener.click("https://x")
    await finish(opener)

    run_open_command.assert_awaited_once()


async def test_the_open_command_is_found_once(open_command: MagicMock) -> None:
    opener = Opener(MagicMock())
    opener.prewarm()

    opener.click("https://x")
    await finish(opener)
    opener.click("https://y")
    await finish(opener)

    open_command.assert_called_once()


async def test_the_moon_makes_a_full_turn() -> None:
    opener = Opener(MagicMock())
    row: StyleAndTextTuples = [("", "branch "), ("", "👍", Icon("https://x"))]
    seen: list[str] = []
    opener.invalidate = lambda: seen.append(texts(opener.spinning(row))[1])

    opener.click("https://x")
    await finish(opener)

    assert seen == [*MOONS, "👍"]


async def test_the_moon_spins_until_the_link_opens(
    run_open_command: AsyncMock,
) -> None:
    opened = asyncio.Event()

    async def wait_until_opened(*_: object) -> None:
        await opened.wait()

    run_open_command.side_effect = wait_until_opened
    opener = Opener(MagicMock())

    opener.click("https://x")
    await asyncio.sleep(len(MOONS) * 0.005)
    assert "https://x" in opener.opening
    opened.set()
    await finish(opener)

    assert "https://x" not in opener.opening


def test_only_icons_of_the_opening_link_spin() -> None:
    opener = Opener(MagicMock())
    opener.opening["https://x"] = 2
    row: StyleAndTextTuples = [
        ("", "branch "),
        ("", "👍", Icon("https://x")),
        ("", "💬", Icon("https://y")),
    ]

    assert texts(opener.spinning(row)) == ["branch ", MOONS[2], "💬"]
