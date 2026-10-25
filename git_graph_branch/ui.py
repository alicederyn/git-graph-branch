"""Presents rendered rows on the terminal, once or continuously."""

import asyncio
import os
import shutil
import sys
import textwrap
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from prompt_toolkit import Application, print_formatted_text
from prompt_toolkit.application import get_app
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import (
    ConditionalContainer,
    Float,
    FloatContainer,
    Layout,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl, UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.output.plain_text import PlainTextOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import DummyStyle, Style

from . import tmux
from .display import Config, Frame
from .links import Icon
from .viewport import Viewport

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

type Rows = Sequence[StyleAndTextTuples]
type ShowFrame = Callable[[Frame], None]
type Refresh = Callable[[ShowFrame], Coroutine[None, None, None]]

STYLE = Style.from_dict(
    {
        "branch.head": "bold ansimagenta",
        # prompt_toolkit spells SGR 90 "ansibrightblack"
        "branch.merged": "ansibrightblack",
        "unmerged": "bold ansired",
        "tooltip": "reverse",
    }
)

TOOLTIP_DELAY = 0.5
"""Seconds the pointer stays on an icon before its tooltip shows, as in GTK."""


def terminal_output(config: Config) -> Output:
    """Build an Output for stdout that obeys --color.

    Constructed directly, as prompt_toolkit's create_output selects on
    stdout.isatty() and thus cannot emit colour into a pipe. The colour depth
    is fixed, as Vt100_Output otherwise drops colour when TERM=dumb.
    """
    if not config.color:
        return PlainTextOutput(sys.stdout)

    def get_size() -> Size:
        size = shutil.get_terminal_size()
        return Size(rows=size.lines, columns=size.columns)

    return Vt100_Output(
        sys.stdout,
        get_size=get_size,
        term=os.environ.get("TERM"),
        default_color_depth=ColorDepth.DEFAULT,
    )


def hyperlinked(row: StyleAndTextTuples) -> StyleAndTextTuples:
    """Make each fragment that has an Icon with a URL into an OSC 8 hyperlink.

    With no mouse reporting, the terminal opens the link on Ctrl-click.
    """
    fragments: StyleAndTextTuples = []
    for style, text, *handler in row:
        if handler and isinstance(handler[0], Icon) and handler[0].url:
            fragments.append(("[ZeroWidthEscape]", f"\x1b]8;;{handler[0].url}\x1b\\"))
            fragments.append((style, text))
            fragments.append(("[ZeroWidthEscape]", "\x1b]8;;\x1b\\"))
        else:
            fragments.append((style, text))
    return fragments


def rows_to_fragments(rows: Rows) -> StyleAndTextTuples:
    """Concatenate the rows into one newline-separated fragment list."""
    fragments: StyleAndTextTuples = []
    for row in rows:
        if fragments:
            fragments.append(("", "\n"))
        fragments.extend(row)
    return fragments


async def show_once(config: Config, refresh: Refresh) -> None:
    """Write each refresh of the rows straight to the terminal.

    Links are written only with colour, as escape sequences are then allowed.
    """
    output = terminal_output(config)

    def show(frame: Frame) -> None:
        rows = [hyperlinked(row) for row in frame.rows] if config.color else frame.rows
        print_formatted_text(
            FormattedText(rows_to_fragments(rows)), style=STYLE, output=output
        )

    await refresh(show)


def fragment_at(row: StyleAndTextTuples, col: int) -> int | None:
    """The index of the fragment that holds the character at col."""
    end = 0
    for index, fragment in enumerate(row):
        end += len(fragment[1])
        if col < end:
            return index
    return None


END_OF_LINE: StyleAndTextTuples = [("", " ")]


def tooltip_of(row: StyleAndTextTuples, index: int) -> str | None:
    handler = row[index][2] if len(row[index]) > 2 else None  # type: ignore[misc]
    return handler.tooltip if isinstance(handler, Icon) else None


class RowsControl(UIControl):
    """Shows the rows that fit the window, at a position the user can scroll.

    One row is one line, so the window is a slice of the row list rather than a
    scrolled Window: prompt_toolkit ties its own vertical scrolling to the
    cursor, which this display does not have.

    The pointer position is kept, not the icon under it, so a new frame or a
    scroll that moves another icon under the pointer starts its own delay.
    """

    def __init__(self, tooltip_delay: float = TOOLTIP_DELAY) -> None:
        self.frame = Frame([], None)
        self.viewport = Viewport()
        self.height = 0
        self.width = 0
        self.lines: Rows = []
        self.tooltip_delay = tooltip_delay
        self.pointer: Point | None = None
        self.hovered: tuple[int, int] | None = None
        """The line and fragment index of the icon with a tooltip under the pointer."""
        self.tooltip_timer: asyncio.TimerHandle | None = None
        self.tooltip_shown = False

    def create_content(self, width: int, height: int) -> UIContent:
        """The visible rows, each with a space after it, and lines of one space
        below them.

        Window gives a click to the nearest character: the last character of
        the row for a click to its right, and the last row for a click below
        the rows. The spaces make sure that these clicks do not find a link.
        """
        self.width = width
        lines = [[*row, *END_OF_LINE] for row in self.visible_rows(height)]
        lines += [END_OF_LINE] * (height - len(lines))
        self.lines = lines
        self.hover()
        return UIContent(
            get_line=lambda i: lines[i],
            line_count=len(lines),
            show_cursor=False,
            menu_position=self.pointer if self.tooltip else None,
        )

    @property
    def tooltip(self) -> str | None:
        """The tooltip to show at the pointer, once the delay has passed."""
        if not self.tooltip_shown or self.hovered is None:
            return None
        y, index = self.hovered
        return tooltip_of(self.lines[y], index)

    def tooltip_target(self) -> tuple[int, int] | None:
        if self.pointer is None or self.pointer.y >= len(self.lines):
            return None
        row = self.lines[self.pointer.y]
        index = fragment_at(row, self.pointer.x)
        if index is None or tooltip_of(row, index) is None:
            return None
        return (self.pointer.y, index)

    def hover(self) -> None:
        """Hide the tooltip if the pointer is on a different fragment, and start
        the delay if that fragment has a tooltip."""
        target = self.tooltip_target()
        if target == self.hovered:
            return
        self.hovered = target
        self.tooltip_shown = False
        if self.tooltip_timer:
            self.tooltip_timer.cancel()
            self.tooltip_timer = None
        if target is not None:
            self.tooltip_timer = asyncio.get_running_loop().call_later(
                self.tooltip_delay, self.show_tooltip
            )
        get_app().invalidate()

    def show_tooltip(self) -> None:
        self.tooltip_timer = None
        self.tooltip_shown = True
        get_app().invalidate()

    def visible_rows(self, height: int) -> Rows:
        """Position the window for this render, and return the rows it shows.

        Only a render knows the window height, so the viewport moves here, and
        the height is kept for scrolling.
        """
        self.height = height
        self.viewport = self.viewport.for_render(
            self.frame.head, len(self.frame.rows), height
        )
        top = self.viewport.top
        return self.frame.rows[top : top + height]

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
        # One line per notch, not a document's three: the branch list and the
        # pane showing it are both expected to be short
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.scroll(-1)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.scroll(1)
            return None
        if mouse_event.event_type == MouseEventType.MOUSE_MOVE:
            self.pointer = mouse_event.position
            self.hover()
            return None
        return self.fragment_mouse_handler(mouse_event)

    def fragment_mouse_handler(self, mouse_event: MouseEvent) -> "NotImplementedOrNone":
        """Pass the event to the mouse handler of the fragment at its position."""
        position = mouse_event.position
        if position.y >= len(self.lines):
            return NotImplemented
        row = self.lines[position.y]
        index = fragment_at(row, position.x)
        if index is None or len(row[index]) < 3:
            return NotImplemented
        return row[index][2](mouse_event)  # type: ignore[misc]


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


def quit_key_bindings() -> KeyBindings:
    """Bind q and Ctrl-C to exit the app.

    In raw mode the terminal sends no SIGINT, so Ctrl-C must be bound.
    """
    key_bindings = KeyBindings()

    @key_bindings.add("q")
    @key_bindings.add("c-c")
    def quit_app(event: KeyPressEvent) -> None:
        event.app.exit()

    return key_bindings


def padded_tooltip(tooltip: str, width: int) -> str:
    """Wrap each line of tooltip at word boundaries to fit width, with a space
    either side.

    Window wraps only at the window edge, which can split a word.
    """
    return "\n".join(
        f" {wrapped} "
        for line in tooltip.split("\n")
        for wrapped in textwrap.wrap(line, max(1, width - 2)) or [""]
    )


def tooltip_float(control: RowsControl) -> Float:
    """A borderless box that shows control's tooltip next to the pointer.

    The control puts the pointer in UIContent.menu_position, and FloatContainer
    places the float below it, or above it if there is no space below.
    """

    def text() -> StyleAndTextTuples:
        return [("", padded_tooltip(control.tooltip or "", control.width))]

    window = Window(
        FormattedTextControl(text), style="class:tooltip", dont_extend_width=True
    )
    return Float(
        ConditionalContainer(window, Condition(lambda: control.tooltip is not None)),
        xcursor=True,
        ycursor=True,
    )


def full_screen_app(config: Config, control: RowsControl) -> Application[None]:
    """Build a full-screen app that displays control, with its tooltip.

    The colour depth is fixed, as prompt_toolkit otherwise drops colour for
    NO_COLOR or TERM=dumb, and an explicit --color must still win.
    """
    return Application(
        layout=Layout(
            FloatContainer(
                Window(control, wrap_lines=False), floats=[tooltip_float(control)]
            )
        ),
        style=STYLE if config.color else DummyStyle(),
        color_depth=ColorDepth.DEFAULT,
        key_bindings=merge_key_bindings(
            [quit_key_bindings(), scroll_key_bindings(control)]
        ),
        full_screen=True,
        mouse_support=True,
    )


@asynccontextmanager
async def background_task(
    coroutine: Coroutine[None, None, None],
) -> AsyncIterator[None]:
    """Run coroutine alongside the body, and cancel it when the body exits.

    If coroutine fails, the body is cancelled and the error is raised in an
    ExceptionGroup.
    """
    async with asyncio.TaskGroup() as tg:
        task = tg.create_task(coroutine)
        try:
            yield
        finally:
            task.cancel()


async def show_watching(config: Config, refresh: Refresh) -> None:
    """Display the rows full-screen, redrawing as each refresh arrives."""
    control = RowsControl()
    app = full_screen_app(config, control)

    def show(frame: Frame) -> None:
        control.frame = frame
        app.invalidate()

    # If refresh fails, the app is cancelled, so it restores the terminal
    async with tmux.watch_window_visibility(), background_task(refresh(show)):
        # SIGINT and SIGTERM stay with cli.handle_signals
        await app.run_async(handle_sigint=False)
