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


class Branch:
    def __init__(self, ref: Path | str):
        self._ref = ref if isinstance(ref, Path) else git_dir() / "refs" / "heads" / ref
        # Used frequently enough to eagerly cache
        self.name = self._ref.relative_to(git_dir() / "refs" / "heads").as_posix()

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"git.Branch({repr(self.name)})"


def branches() -> Iterable[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
