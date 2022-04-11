import sys
from argparse import ArgumentParser
from logging import getLogger

from .log_config import configure_logging

LOG = getLogger(__name__)


def argument_parser() -> ArgumentParser:
    p = ArgumentParser(
        prog="git-graph-branch", description="Pretty-print branch metadata"
    )
    return p


def main() -> None:
    configure_logging()
    try:
        argument_parser().parse_args()
        from .git import branches
        from .git.config import config

        bs = tuple(branches())
        print(bs)
        for b in bs:
            if b.is_head:
                print("HEAD:", end=" ")
            print(b.name, end=" ")
            if b.upstream:
                print("upstream:" + b.upstream.name, end=" ")
            print()
        print(config())
    except Exception as e:
        LOG.fatal(str(e))
        sys.exit(1)
