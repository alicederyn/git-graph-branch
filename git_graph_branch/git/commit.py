from collections.abc import Iterator

from .decode import decompress
from .object import GitObject
from .pack import ObjectKind, packs
from .path import git_dir


class Missing:
    pass


class MissingCommit(Exception):
    pass


class Commit:
    def __init__(self, hash: str):
        self.hash = hash
        self._cached_git_object: GitObject | Missing | None = None

    @property
    def parents(self) -> "tuple[Commit, ...]":
        return tuple(Commit(hash) for hash in self._git_object().parents)

    def available_parents(self) -> "Iterator[Commit]":
        for hash in self._git_object().parents:
            try:
                yield Commit(hash)
            except MissingCommit:
                continue

    @property
    def first_parent(self) -> "Commit | None":
        hash = self._git_object().first_parent
        return Commit(hash) if hash else None

    @property
    def message(self) -> bytes:
        return self._git_object().message

    @property
    def commit_date(self) -> int:
        """The commit date.

        This is not preserved across rebases and cherry-picks.
        """
        return self._git_object().commit_date

    @property
    def timestamp(self) -> int:
        """The author date of the commit.

        This (unlike the commit date) is preserved across rebases and cherry-picks.
        """
        return self._git_object().timestamp

    def _git_object(self) -> GitObject:
        if self._cached_git_object is None:
            filename = git_dir() / "objects" / self.hash[:2] / self.hash[2:]
            try:
                with open(filename, "rb") as f:
                    data = decompress(f)
            except FileNotFoundError:
                try:
                    kind, data = packs()[self.hash]
                    if kind != ObjectKind.COMMIT:
                        raise KeyError()
                except KeyError:
                    self._cached_git_object = Missing()
            self._cached_git_object = GitObject.decode(data)
        if isinstance(self._cached_git_object, Missing):
            raise MissingCommit("Shallow clone: commit not found: " + self.hash)
        return self._cached_git_object

    def __str__(self) -> str:
        return self.hash[:10]

    def __repr__(self) -> str:
        return f"git.Commit({repr(self.hash)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Commit):
            return other.hash == self.hash
        return False

    def __hash__(self) -> int:
        return hash(self.hash)
