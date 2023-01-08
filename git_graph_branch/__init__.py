import sys
from argparse import ArgumentParser
from logging import getLogger
from typing import Sequence, TypeVar

from .dag import layout
from .git import branches
from .log_config import configure_logging

LOG = getLogger(__name__)
T = TypeVar("T")


def argument_parser() -> ArgumentParser:
    p = ArgumentParser(
        prog="git-graph-branch", description="Pretty-print branch metadata"
    )
    return p


def optional_to_iterable(value: T | None) -> list[T]:
    return [value] if value is not None else []


def main(args: Sequence[str] | None = None) -> None:
    configure_logging()
    try:
        argument_parser().parse_args(args)

        art_and_branches = layout(
            branches(),
            get_parents=lambda b: optional_to_iterable(b.upstream),
            key=lambda b: (b.timestamp, b.name),
        )

        for art, b in art_and_branches:
            print(f"{art}  {b.name}")
    except Exception as e:
        LOG.fatal(str(e))
        sys.exit(1)
