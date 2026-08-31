"""Presents rendered rows on the terminal, once or continuously."""

import asyncio
import os
import shutil
import sys
from collections.abc import Callable, Coroutine, Sequence
from typing import TYPE_CHECKING

from prompt_toolkit import Application, print_formatted_text
from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.output import Output
from prompt_toolkit.output.plain_text import PlainTextOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import DummyStyle, Style

from .display import Config, Frame
from .viewport import Viewport

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

type Rows = Sequence[StyleAndTextTuples]
type ShowFrame = Callable[[Frame], None]
type Refresh = Callable[[ShowFrame], Coroutine[None, None, None]]

STYLE = Style.from_dict(
    {
        "branch.head": "bold ansimagenta",
        # prompt_toolkit spells SGR 37 "ansigray"; its "ansiwhite" is SGR 97
        "branch.merged": "ansigray",
        "unmerged": "bold ansired",
    }
)


def terminal_output(config: Config) -> Output:
    """Build an Output for stdout that obeys --color.

    Constructed directly, as prompt_toolkit's create_output selects on
    stdout.isatty() and thus cannot emit colour into a pipe.
    """
    if not config.color:
        return PlainTextOutput(sys.stdout)

    def get_size() -> Size:
        size = shutil.get_terminal_size()
        return Size(rows=size.lines, columns=size.columns)

    return Vt100_Output(sys.stdout, get_size=get_size, term=os.environ.get("TERM"))


def rows_to_fragments(rows: Rows) -> StyleAndTextTuples:
    """Concatenate the rows into one newline-separated fragment list."""
    fragments: StyleAndTextTuples = []
    for row in rows:
        if fragments:
            fragments.append(("", "\n"))
        fragments.extend(row)
    return fragments


async def show_once(config: Config, refresh: Refresh) -> None:
    """Write each refresh of the rows straight to the terminal."""
    output = terminal_output(config)

    def show(frame: Frame) -> None:
        print_formatted_text(
            FormattedText(rows_to_fragments(frame.rows)), style=STYLE, output=output
        )

    await refresh(show)


class RowsControl(UIControl):
    """Shows the rows that fit the window, at a position the user can scroll.

    One row is one line, so the window is a slice of the row list rather than a
    scrolled Window: prompt_toolkit ties its own vertical scrolling to the
    cursor, which this display does not have.
    """

    def __init__(self) -> None:
        self.frame = Frame([], None)
        self.viewport = Viewport()
        self.height = 0

    def create_content(self, width: int, height: int | None) -> UIContent:
        if height is None:
            # The preferred_height path asks how tall the whole content is
            return UIContent(
                get_line=lambda i: self.frame.rows[i],
                line_count=len(self.frame.rows),
                show_cursor=False,
            )
        self.height = height
        self.viewport = self.viewport.for_render(
            self.frame.head, len(self.frame.rows), height
        )
        top = self.viewport.top
        lines = self.frame.rows[top : top + height]
        return UIContent(
            get_line=lambda i: lines[i], line_count=len(lines), show_cursor=False
        )

    def scroll(self, lines: int) -> None:
        self.viewport = self.viewport.scrolled(
            lines, self.frame.head, len(self.frame.rows), self.height
        )

    def scroll_pages(self, pages: int) -> None:
        self.scroll(pages * self.height)

    def to_top(self) -> None:
        self.scroll(-len(self.frame.rows))

    def to_bottom(self) -> None:
        self.scroll(len(self.frame.rows))

    def mouse_handler(self, mouse_event: MouseEvent) -> "NotImplementedOrNone":
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.scroll(-1)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.scroll(1)
            return None
        return NotImplemented


def scroll_key_bindings(control: RowsControl) -> KeyBindings:
    key_bindings = KeyBindings()

    def bind(key: str, scroll: Callable[[], None]) -> None:
        @key_bindings.add(key)
        def _(event: KeyPressEvent) -> None:
            scroll()

    bind("up", lambda: control.scroll(-1))
    bind("down", lambda: control.scroll(1))
    bind("pageup", lambda: control.scroll_pages(-1))
    bind("pagedown", lambda: control.scroll_pages(1))
    bind("home", control.to_top)
    bind("end", control.to_bottom)
    return key_bindings


async def show_watching(config: Config, refresh: Refresh) -> None:
    """Display the rows full-screen, redrawing as each refresh arrives."""
    control = RowsControl()

    key_bindings = scroll_key_bindings(control)

    # In raw mode the terminal sends no SIGINT, so Ctrl-C must be bound
    @key_bindings.add("q")
    @key_bindings.add("c-c")
    def quit_app(event: KeyPressEvent) -> None:
        event.app.exit()

    app: Application[None] = Application(
        layout=Layout(Window(control, wrap_lines=False)),
        style=STYLE if config.color else DummyStyle(),
        key_bindings=key_bindings,
        full_screen=True,
        mouse_support=True,
    )

    def show(frame: Frame) -> None:
        control.frame = frame
        app.invalidate()

    # The TaskGroup cancels run_async if refresh fails, so the app restores the
    # terminal
    async with asyncio.TaskGroup() as tg:
        task = tg.create_task(refresh(show))
        try:
            # SIGINT and SIGTERM stay with cli.handle_signals
            await app.run_async(handle_sigint=False)
        finally:
            task.cancel()
