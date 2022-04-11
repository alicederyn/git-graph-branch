from functools import cache
from pathlib import Path
from typing import Iterable


def path_and_parents(p: Path) -> Iterable[Path]:
    yield p
    while p.parent != p:
        p = p.parent
        yield p


@cache
def git_dir() -> Path:
    for p in path_and_parents(Path.cwd()):
        d = p / ".git"
        if d.is_dir():
            return d
    raise Exception("not a git repository (or any of the parent directories): .git")
