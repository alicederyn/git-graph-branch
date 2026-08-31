import asyncio
import pdb
import signal
import sys
from argparse import SUPPRESS, ArgumentParser
from contextlib import suppress
from datetime import timedelta
from logging import getLogger
from types import TracebackType
from typing import Sequence, Type, TypeVar

from .display import Config, graph_rows
from .nix import once, watcher
from .ui import ShowRows, show_once, show_watching

LOG = getLogger(__name__)
T = TypeVar("T")


def parse_args(args: Sequence[str] | None, *, is_tty: bool) -> Config:
    defaults = Config(is_tty=is_tty)
    p = ArgumentParser(
        prog="git-graph-branch", description="Pretty-print branch metadata"
    )
    p.add_argument(
        "--color",
        action="store_true",
        dest="color",
        default=defaults.color,
        help="Display colorized output; defaults to true if the output is a TTY",
    )
    p.add_argument("--no-color", action="store_false", dest="color", help=SUPPRESS)
    p.add_argument(
        "--remote-icons",
        action="store_true",
        dest="remote_icons",
        default=defaults.remote_icons,
        help="Display remote status icon; defaults to true if the output is a TTY",
    )
    p.add_argument(
        "--no-remote-icons", action="store_false", dest="remote_icons", help=SUPPRESS
    )
    p.add_argument("--pdb", action="store_true", dest="pdb", help=SUPPRESS)
    if is_tty:
        watch = p.add_argument_group("watch options")
        watch.add_argument(
            "-w",
            "--watch",
            action="store_true",
            dest="watch",
            default=defaults.watch,
            help="Watch for changes and keep the graph updated",
        )
        watch.add_argument(
            "--poll-every",
            type=float,
            dest="poll_every",
            metavar="SECS",
            default=defaults.poll_every,
            help="If watching, how often to poll for changes (default: %(default)s)",
        )
    return p.parse_args(args=args, namespace=defaults)


def invoke_pdb_excepthook(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Invoke pdb on uncaught exceptions."""
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
    pdb.post_mortem(exc_traceback)


def optional_to_iterable(value: T | None) -> list[T]:
    return [value] if value is not None else []


async def handle_signals() -> None:
    """Handle SIGINT and SIGTERM by cancelling the main task."""
    task = asyncio.current_task()
    assert task

    def cancel_task() -> None:
        task.cancel()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, cancel_task)
    loop.add_signal_handler(signal.SIGTERM, cancel_task)


async def graph_branches(config: Config) -> None:
    async def refresh(show: ShowRows) -> None:
        async with (
            watcher(timedelta(seconds=config.poll_every)) if config.watch else once()
        ) as needs_refresh:
            while await needs_refresh():
                show(graph_rows(config))

    show_ui = show_watching if config.watch else show_once
    await show_ui(config, refresh)


async def amain(args: Sequence[str] | None = None) -> None:
    await handle_signals()
    with suppress(asyncio.CancelledError):
        is_tty = sys.stdout.isatty()
        config = parse_args(args, is_tty=is_tty)
        if config.pdb:
            sys.excepthook = invoke_pdb_excepthook

        await graph_branches(config)
