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

from .dag import layout
from .display import Config, print_branch
from .git import branches, compute_branch_dag
from .nix import once, watcher

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


def clear_screen() -> None:
    # Clear the screen and move cursor to top-left corner
    sys.stdout.write("\x1b[2J\x1b[0;0H")
    sys.stdout.flush()


async def graph_branches(config: Config) -> None:
    async with (
        watcher(timedelta(seconds=config.poll_every)) if config.watch else once()
    ) as needs_refresh:
        while await needs_refresh():
            if config.watch:
                clear_screen()
            dag = compute_branch_dag(list(branches()))
            art_and_branches = layout(dag, key=lambda b: (b.timestamp, b.name))

            for art, b in art_and_branches:
                print_branch(art, b, config, dag.parents(b))
            sys.stdout.flush()


async def amain(args: Sequence[str] | None = None) -> None:
    await handle_signals()
    with suppress(asyncio.CancelledError):
        is_tty = sys.stdout.isatty()
        config = parse_args(args, is_tty=is_tty)
        if config.pdb:
            sys.excepthook = invoke_pdb_excepthook

        await graph_branches(config)
