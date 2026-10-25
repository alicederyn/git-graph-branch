"""Icons that link to a page, opened in the browser on Ctrl+left-click, or show
a tooltip on hover."""

import asyncio
import itertools
import os
import shutil
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from subprocess import DEVNULL
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.mouse_events import (
    MouseButton,
    MouseEvent,
    MouseEventType,
    MouseModifier,
)

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

MOONS = "🌘🌗🌖🌕🌔🌓🌒🌑"
MOON_SECONDS = 0.1

OPEN_TIMEOUT = 5.0
"""Seconds to wait for the open command to exit.

xdg-open runs a native browser in the foreground, so it may not exit until
the browser does.
"""


def open_in_background(url: str) -> None:
    """Open url, unless the only browser runs in the terminal.

    webbrowser falls back to a console browser such as lynx when there is no
    display, and it would take over the terminal and block the event loop.
    """
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return
    if type(browser) is webbrowser.GenericBrowser:
        return
    browser.open(url)


def open_command() -> list[str] | None:
    """The command that opens a URL, with %s in place of the URL, or None if
    webbrowser must open it.

    This is slow on WSL, as each PATH lookup searches the Windows directories
    on PATH, which WSL reads over 9p.

    On WSL, explorer.exe opens the Windows default browser. webbrowser would
    pick xdg-open, which goes through wslview, which starts powershell.exe.
    """
    if "WSL_DISTRO_NAME" in os.environ and "BROWSER" not in os.environ:
        explorer = shutil.which("explorer.exe")
        if explorer:
            return [explorer, "%s"]
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return None
    if type(browser) is webbrowser.BackgroundBrowser:
        return [browser.name, *browser.args]
    return None


async def run_open_command(command: list[str], url: str) -> None:
    """Run command for url, and wait until it exits, or for OPEN_TIMEOUT.

    The exit code is ignored, as explorer.exe exits with 1 when it succeeds.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *(arg.replace("%s", url) for arg in command),
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return
    try:
        await asyncio.wait_for(process.wait(), OPEN_TIMEOUT)
    except TimeoutError:
        pass


class Opener:
    """Opens links off the event loop, and spins the moon on each icon of a link
    until it has opened.

    A link that is opening cannot be opened again, so a double-click opens one
    page. The moon makes at least one full turn, so the user sees the click.
    """

    def __init__(self, invalidate: Callable[[], None]) -> None:
        self.invalidate = invalidate
        self.opening: dict[str, int] = {}
        """The moon index of each URL that is opening."""
        self.command: asyncio.Task[list[str] | None] | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    def prewarm(self) -> None:
        """Find the open command now, so the first click does not wait for it."""
        self.open_command()

    def open_command(self) -> asyncio.Task[list[str] | None]:
        if self.command is None:
            self.command = asyncio.create_task(asyncio.to_thread(open_command))
        return self.command

    def click(self, url: str) -> None:
        if url in self.opening:
            return
        self.opening[url] = 0
        self.invalidate()
        task = asyncio.create_task(self.spin(url))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def spin(self, url: str) -> None:
        opened = asyncio.create_task(self.open(url))
        try:
            for moon in itertools.count(1):
                await asyncio.sleep(MOON_SECONDS)
                if moon >= len(MOONS) and opened.done():
                    break
                self.opening[url] = moon % len(MOONS)
                self.invalidate()
            await opened
        finally:
            opened.cancel()
            del self.opening[url]
            self.invalidate()

    async def open(self, url: str) -> None:
        command = await self.open_command()
        if command is None:
            await asyncio.to_thread(open_in_background, url)
        else:
            await run_open_command(command, url)

    def spinning(self, row: StyleAndTextTuples) -> StyleAndTextTuples:
        """row, with a moon in place of each icon whose link is opening."""
        fragments: StyleAndTextTuples = []
        for style, text, *handler in row:
            if handler and isinstance(handler[0], Icon) and handler[0].url:
                moon = self.opening.get(handler[0].url)
                fragments.append(
                    (style, text if moon is None else MOONS[moon], handler[0])
                )
            elif handler:
                fragments.append((style, text, handler[0]))
            else:
                fragments.append((style, text))
        return fragments


@dataclass(frozen=True)
class Icon:
    """The link and tooltip of an icon fragment.

    RowsControl handles the mouse for icons, as it needs the pointer position
    for the tooltip and the Opener for the link. Icon is callable only because
    a fragment holds a mouse handler.
    """

    url: str | None = None
    tooltip: str | None = None

    def __call__(self, mouse_event: MouseEvent) -> "NotImplementedOrNone":
        return NotImplemented

    def opens_on(self, mouse_event: MouseEvent) -> bool:
        return (
            self.url is not None
            and mouse_event.event_type == MouseEventType.MOUSE_DOWN
            and mouse_event.button == MouseButton.LEFT
            and MouseModifier.CONTROL in mouse_event.modifiers
        )
