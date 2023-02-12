import asyncio
import sys
from argparse import SUPPRESS, ArgumentParser
from logging import getLogger
from typing import Sequence, TypeVar

from .dag import layout
from .display import Config, clear_screen, print_branch
from .git import branches
from .ixnay import AsyncNixer, Nixer, SingleUseNixer
from .log_config import configure_logging

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
        "-w",
        "--watch",
        action="store_true",
        help="Watch filesystem for changes and redraw the graph",
    )
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
    return p.parse_args(args=args, namespace=defaults)


def optional_to_iterable(value: T | None) -> list[T]:
    return [value] if value is not None else []


def display_graph(nixer: Nixer, config: Config) -> None:
    art_and_branches = layout(
        branches(nixer),
        get_parents=lambda b: optional_to_iterable(b.upstream(nixer)),
        key=lambda b: (b.timestamp(nixer), b.name),
    )

    for art, b in art_and_branches:
        print_branch(nixer, art, b, config)


async def watch_graph(config: Config) -> None:
    while True:
        nixer = AsyncNixer()
        clear_screen()
        display_graph(nixer, config)
        await nixer.wait_until_nixed()


def main(args: Sequence[str] | None = None) -> None:
    is_tty = sys.stdout.isatty()
    configure_logging()
    try:
        config = parse_args(args, is_tty=is_tty)
        if not config.watch:
            display_graph(SingleUseNixer(), config)
        else:
            try:
                asyncio.run(watch_graph(config))
            except KeyboardInterrupt:
                pass

    except Exception as e:
        LOG.exception(str(e))
        sys.exit(1)
