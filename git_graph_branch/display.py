from argparse import Namespace
from typing import Any

from ansi import color

from .dag import NodeArt
from .git.branch import Branch


class Config(Namespace):
    color: bool
    is_tty: bool

    def __init__(self, *, is_tty: bool = False, **kwargs: Any) -> None:
        defaults = {"color": is_tty}
        super().__init__(**(kwargs | defaults), is_tty=is_tty)


def print_branch(art: NodeArt, b: Branch, config: Config) -> None:
    print(f"{art}  ", end="")
    reset = False
    if config.color and b.is_head:
        print(color.fg.magenta, end="")
        reset = True
    print(b, end="")
    if reset:
        print(color.fx.reset, end="")
    print()
