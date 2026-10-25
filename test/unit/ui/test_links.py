import asyncio
import webbrowser
from collections.abc import Iterator
from subprocess import DEVNULL
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import (
    MouseButton,
    MouseEvent,
    MouseEventType,
    MouseModifier,
)

from git_graph_branch.links import Icon, open_command, run_open_command


@pytest.fixture(autouse=True)
def environ() -> Iterator[dict[str, str]]:
    with patch.dict("os.environ", clear=True) as environ:
        yield environ


@pytest.fixture(autouse=True)
def which() -> Iterator[MagicMock]:
    with patch("shutil.which", return_value="/mnt/c/WINDOWS/explorer.exe") as mock:
        yield mock


@pytest.fixture(autouse=True)
def webbrowser_get() -> Iterator[MagicMock]:
    with patch(
        "webbrowser.get",
        return_value=webbrowser.BackgroundBrowser(["xdg-open", "%s"]),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def create_subprocess_exec() -> Iterator[AsyncMock]:
    with patch("asyncio.create_subprocess_exec") as mock:
        yield mock


@pytest.fixture
def wsl(environ: dict[str, str]) -> None:
    environ["WSL_DISTRO_NAME"] = "Ubuntu"


def click(*modifiers: MouseModifier) -> MouseEvent:
    return MouseEvent(
        position=Point(x=0, y=0),
        event_type=MouseEventType.MOUSE_DOWN,
        button=MouseButton.LEFT,
        modifiers=frozenset(modifiers),
    )


def test_ctrl_click_opens_the_link() -> None:
    assert Icon("https://x").opens_on(click(MouseModifier.CONTROL))


def test_plain_click_does_not_open_the_link() -> None:
    assert not Icon("https://x").opens_on(click())


def test_ctrl_click_without_a_url_opens_nothing() -> None:
    assert not Icon(tooltip="tip").opens_on(click(MouseModifier.CONTROL))


@pytest.mark.usefixtures("wsl")
def test_wsl_opens_links_with_explorer() -> None:
    assert open_command() == ["/mnt/c/WINDOWS/explorer.exe", "%s"]


@pytest.mark.usefixtures("wsl")
def test_wsl_obeys_browser(environ: dict[str, str]) -> None:
    environ["BROWSER"] = "firefox"

    assert open_command() == ["xdg-open", "%s"]


@pytest.mark.usefixtures("wsl")
def test_wsl_without_explorer_uses_webbrowser(which: MagicMock) -> None:
    which.return_value = None

    assert open_command() == ["xdg-open", "%s"]


def test_a_background_browser_gives_its_command() -> None:
    assert open_command() == ["xdg-open", "%s"]


def test_a_console_browser_is_left_to_webbrowser(webbrowser_get: MagicMock) -> None:
    webbrowser_get.return_value = webbrowser.GenericBrowser("lynx")

    assert open_command() is None


def test_no_browser_is_left_to_webbrowser(webbrowser_get: MagicMock) -> None:
    webbrowser_get.side_effect = webbrowser.Error

    assert open_command() is None


async def test_the_open_command_gets_the_url(create_subprocess_exec: AsyncMock) -> None:
    await run_open_command(["open", "--url=%s"], "https://x")

    create_subprocess_exec.assert_awaited_once_with(
        "open",
        "--url=https://x",
        stdin=DEVNULL,
        stdout=DEVNULL,
        stderr=DEVNULL,
        start_new_session=True,
    )
    create_subprocess_exec.return_value.wait.assert_awaited_once()


async def test_a_missing_open_command_is_ignored(
    create_subprocess_exec: AsyncMock,
) -> None:
    create_subprocess_exec.side_effect = FileNotFoundError

    await run_open_command(["open", "%s"], "https://x")


async def test_an_open_command_that_does_not_exit_stops_the_wait(
    create_subprocess_exec: AsyncMock,
) -> None:
    create_subprocess_exec.return_value.wait = asyncio.Event().wait

    with patch("git_graph_branch.links.OPEN_TIMEOUT", 0):
        await run_open_command(["open", "%s"], "https://x")
