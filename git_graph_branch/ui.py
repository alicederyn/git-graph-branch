"""Presents rendered rows on the terminal, once or continuously."""

import asyncio
import os
import shutil
import sys
from collections.abc import Callable, Coroutine, Sequence

from prompt_toolkit import Application, print_formatted_text
from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import Output
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

    def show(rows: Rows) -> None:
        print_formatted_text(
            FormattedText(rows_to_fragments(rows)), style=STYLE, output=output
        )

    await refresh(show)


async def show_watching(config: Config, refresh: Refresh) -> None:
    """Display the rows full-screen, redrawing as each refresh arrives."""
    empty: StyleAndTextTuples = []
    control = FormattedTextControl(empty)

    key_bindings = KeyBindings()

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
    )

    # Fragments are built here, not in a render callback, so they are built
    # inside the nix context manager that produced the rows
    def show(rows: Rows) -> None:
        control.text = rows_to_fragments(rows)
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
