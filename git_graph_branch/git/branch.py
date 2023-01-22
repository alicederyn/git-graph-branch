from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Iterable, TypeGuard, TypeVar, overload

from .commit import Commit
from .config import config
from .path import git_dir

T = TypeVar("T")


def all_instances(items: tuple[Any, ...], _type: type[T]) -> TypeGuard[tuple[T, ...]]:
    return all(isinstance(v, _type) for v in items)


@cache
def git_head() -> str:
    return (git_dir() / "HEAD").open(encoding="utf-8").read().strip()


class Ref:
    def __init__(self, ref: Path) -> None:
        self._ref = ref
        self._relative_ref = self._ref.relative_to(git_dir() / "refs")
        # Lazily cached
        self._cached_commit: Commit | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Ref):
            return other._ref == self._ref
        return False

    def __hash__(self) -> int:
        return hash(self._ref)

    @property
    def commit(self) -> Commit:
        if self._cached_commit is None:
            with open(self._ref, "r", encoding="ascii") as f:
                self._cached_commit = Commit(f.readline().strip())
        return self._cached_commit

    @property
    def timestamp(self) -> int:
        return self.commit.timestamp

    def reflog_reversed(self) -> Iterable[Commit]:
        reflog = git_dir() / "logs" / "refs" / self._relative_ref
        with open(reflog, "rb") as f:
            while f.read(41):
                hash = f.read(40)
                yield Commit(hash.decode("ascii"))
                f.readline()  # Skip to next line


class RemoteBranch(Ref):
    @overload
    def __init__(self, path: Path, /) -> None:
        ...

    @overload
    def __init__(self, remote: str, branch: str, /) -> None:
        ...

    def __init__(self, *args: Path | str) -> None:
        if len(args) == 1:
            ref = args[0]
            assert isinstance(ref, Path)
        else:
            ref = (git_dir() / "refs" / "remotes").joinpath(*args)
        super().__init__(ref)
        self.remote, *subdirs = ref.relative_to(git_dir() / "refs" / "remotes").parts
        self.name = Path(*subdirs).as_posix()

    def __str__(self) -> str:
        return f"{self.remote}/{self.name}"

    def __repr__(self) -> str:
        return f"git.RemoteBranch({repr(self.remote)}, {repr(self.name)})"


class Branch(Ref):
    def __init__(self, ref: Path | str) -> None:
        super().__init__(
            ref if isinstance(ref, Path) else git_dir() / "refs" / "heads" / ref
        )
        # Used frequently enough to eagerly cache
        self.name = self._ref.relative_to(git_dir() / "refs" / "heads").as_posix()

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"git.Branch({repr(self.name)})"

    @property
    def is_head(self) -> bool:
        return git_head() == f"ref: refs/heads/{self.name}"

    @property
    def upstream(self) -> Branch | RemoteBranch | None:
        c = config().get(("branch", self.name), {})
        remote = c.get("remote", ".")
        merge = c.get("merge")
        if not merge:
            return None
        if not merge.startswith("refs/heads/"):
            raise AssertionError(
                f'Unexpected config: [branch "{self.name}"].merge does not start `refs/heads/`'
            )
        upstream_name = merge.removeprefix("refs/heads/")
        if remote == ".":
            return Branch(upstream_name)
        else:
            return RemoteBranch(remote, upstream_name)


def branches() -> Iterable[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
