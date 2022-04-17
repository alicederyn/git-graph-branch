from functools import cache
from pathlib import Path
from typing import Iterable

from .commit import Commit
from .config import config
from .path import git_dir


@cache
def git_head() -> str:
    return (git_dir() / "HEAD").open(encoding="utf-8").read().strip()


class Branch:
    def __init__(self, ref: Path | str):
        self._ref = ref if isinstance(ref, Path) else git_dir() / "refs" / "heads" / ref
        # Used frequently enough to eagerly cache
        self.name = self._ref.relative_to(git_dir() / "refs" / "heads").as_posix()

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"git.Branch({repr(self.name)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Branch):
            return other._ref == self._ref
        return False

    def __hash__(self) -> int:
        return hash(self._ref)

    @property
    def is_head(self) -> bool:
        return git_head() == f"ref: refs/heads/{self.name}"

    @property
    def commit(self) -> Commit:
        with open(self._ref, "r", encoding="ascii") as f:
            return Commit(f.readline().strip())

    @property
    def upstream(self) -> "Branch | None":
        c = config().get(("branch", self.name), {})
        remote = c.get("remote", ".")
        merge = c.get("merge")
        if not merge:
            return None
        if remote == "." and merge.startswith("refs/heads/"):
            b = merge.removeprefix("refs/heads/")
            return Branch(b)
        # TODO: Handle remote branches
        return None

    def reflog_reversed(self) -> Iterable[Commit]:
        reflog = git_dir() / "logs" / "refs" / "heads" / self.name
        with open(reflog, "rb") as f:
            while f.read(41):
                hash = f.read(40)
                yield Commit(hash.decode("ascii"))
                f.readline()  # Skip to next line


def branches() -> Iterable[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
