"""Presents rendered rows on the terminal, once or continuously."""

import asyncio
import os
import shutil
import sys
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager

from prompt_toolkit import Application, print_formatted_text
from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.output.plain_text import PlainTextOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import DummyStyle, Style

from .display import Config

type Rows = Sequence[StyleAndTextTuples]
type ShowRows = Callable[[Rows], None]
type Refresh = Callable[[ShowRows], Coroutine[None, None, None]]

STYLE = Style.from_dict(
    {
        "branch.head": "bold ansimagenta",
        # prompt_toolkit spells SGR 90 "ansibrightblack"
        "branch.merged": "ansibrightblack",
        "unmerged": "bold ansired",
    }
)


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

    def show(rows: Rows) -> None:
        print_formatted_text(
            FormattedText(rows_to_fragments(rows)), style=STYLE, output=output
        )

    await refresh(show)


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


def full_screen_app(config: Config, control: FormattedTextControl) -> Application[None]:
    """Build a full-screen app that displays control.

    The colour depth is fixed, as prompt_toolkit otherwise drops colour for
    NO_COLOR or TERM=dumb, and an explicit --color must still win.
    """
    return Application(
        layout=Layout(Window(control, wrap_lines=False)),
        style=STYLE if config.color else DummyStyle(),
        color_depth=ColorDepth.DEFAULT,
        key_bindings=quit_key_bindings(),
        full_screen=True,
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
    empty: StyleAndTextTuples = []
    control = FormattedTextControl(empty)
    app = full_screen_app(config, control)

    def show(rows: Rows) -> None:
        control.text = rows_to_fragments(rows)
        app.invalidate()

    # If refresh fails, the app is cancelled, so it restores the terminal
    async with background_task(refresh(show)):
        # SIGINT and SIGTERM stay with cli.handle_signals
        await app.run_async(handle_sigint=False)
