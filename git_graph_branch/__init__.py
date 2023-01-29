import sys
from argparse import SUPPRESS, ArgumentParser
from logging import getLogger
from typing import Sequence, TypeVar

from .dag import layout
from .display import Config, print_branch
from .git import branches
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


def main(args: Sequence[str] | None = None) -> None:
    is_tty = sys.stdout.isatty()
    configure_logging()
    try:
        config = parse_args(args, is_tty=is_tty)

        art_and_branches = layout(
            branches(),
            get_parents=lambda b: optional_to_iterable(b.upstream),
            key=lambda b: (b.timestamp, b.name),
        )

        for art, b in art_and_branches:
            print_branch(art, b, config)
    except Exception as e:
        LOG.fatal(str(e))
        sys.exit(1)
