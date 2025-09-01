from __future__ import annotations

from functools import cache, cached_property
from pathlib import Path
from typing import Any, Iterator, TypeGuard, TypeVar, overload

from .commit import Commit
from .config import config
from .path import git_dir
from .reflog import ReflogEntry, iter_reflog

T = TypeVar("T")


def all_instances(items: tuple[Any, ...], _type: type[T]) -> TypeGuard[tuple[T, ...]]:
    return all(isinstance(v, _type) for v in items)


@cache
def git_head() -> str:
    return (git_dir() / "HEAD").open(encoding="utf-8").read().strip()


@cache
def packed_refs() -> dict[Path, Commit]:
    def get_path(line: str) -> Path:
        path = Path(line.split(" ")[1].strip())
        return path.relative_to("refs/")

    def get_commit(line: str) -> Commit:
        return Commit(line.split(" ")[0])

    path = git_dir() / "packed-refs"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {
                get_path(line): get_commit(line)
                for line in f
                if not line.startswith("#")  # comment
                and not line.startswith("^")  # peeled ref (used for tags)
            }
    except FileNotFoundError:
        return {}


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

    def exists(self) -> bool:
        """Whether this reference exists."""
        return self._ref.exists() or self._relative_ref in packed_refs()

    @cached_property
    def commit(self) -> Commit:
        try:
            with open(self._ref, "r", encoding="ascii") as f:
                return Commit(f.readline().strip())
        except FileNotFoundError:
            commit = packed_refs().get(self._relative_ref)
            if commit is not None:
                return commit
            raise

    @property
    def timestamp(self) -> int:
        return self.commit.timestamp

    def reflog(self) -> Iterator[ReflogEntry]:
        reflog = git_dir() / "logs" / "refs" / self._relative_ref
        return iter_reflog(reflog)


class RemoteBranch(Ref):
    @overload
    def __init__(self, path: Path, /) -> None: ...

    @overload
    def __init__(self, remote: str, branch: str, /) -> None: ...

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
            b = RemoteBranch(remote, upstream_name)
            # Sometimes remote branches can be deleted without properly updating
            # the upstream link.
            return b if b.exists() else None


def branches() -> Iterator[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
