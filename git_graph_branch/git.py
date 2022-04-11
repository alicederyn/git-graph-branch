import re
import zlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Iterable


def path_and_parents(p: Path) -> Iterable[Path]:
    yield p
    while p.parent != p:
        p = p.parent
        yield p


Config = dict[str | tuple[str, str], dict[str, str]]


def parse_config(lines: Iterable[str]) -> Config:
    SINGLE_STRING_KEY = re.compile(r"^\[(\S+)\](\s*#.*)?$")
    DOUBLE_STRING_KEY = re.compile(r'^\[(\S+)\s+"([^\\"]*(\\.[^\\"]*)*)"\](\s*#.*)?$')
    KEY_VALUE = re.compile(r"^(\w+)\s*=\s*([^\"#\s]([^#]*[^#\s])?)(\s*#.*)?$")
    KEY_QUOTED_VALUE = re.compile(r'^(\w+)\s*=\s*"([^\\"]*(\\.[^\\"]*)*)"(\s*#.*)?$')
    BLANK = re.compile(r"^(#.*)?$")
    result: Config = {}
    current_dict: dict[str, str] | None = None
    for line in lines:
        line = line.strip()
        if m := SINGLE_STRING_KEY.match(line):
            key = m.group(1)
            current_dict = result.setdefault(key, {})
        elif m := DOUBLE_STRING_KEY.match(line):
            key = (m.group(1), m.group(2).encode("utf-8").decode("unicode_escape"))
            current_dict = result.setdefault(key, {})
        elif BLANK.match(line):
            pass
        elif current_dict is not None:
            if m := (KEY_VALUE.match(line) or KEY_QUOTED_VALUE.match(line)):
                current_dict[m.group(1)] = (
                    m.group(2).encode("utf-8").decode("unicode_escape")
                )
            else:
                raise Exception("Error parsing .git/config\nUnexpected line: " + line)
        else:
            raise Exception("Error parsing .git/config\nUnexpected line: " + line)

    return result


def decompress(commit: Iterable[bytes]) -> bytes:
    z = zlib.decompressobj(zlib.MAX_WBITS)
    decompressed: list[bytes] = []
    for compressed in commit:
        decompressed.append(z.decompress(compressed))
    decompressed.append(z.flush())
    return b"".join(decompressed)


@dataclass
class GitObject:
    parents: tuple[str, ...]
    message: bytes

    @property
    def first_parent(self) -> str | None:
        return self.parents[0] if self.parents else None

    @classmethod
    def decode(cls, commit: Iterable[bytes]) -> "GitObject":
        """Parses a git commit object for metadata"""
        raw = decompress(commit)
        parents: list[str] = []
        lines = iter(raw[raw.find(b"\0") + 1 :].split(b"\n"))
        while line := next(lines):
            if line.startswith(b"parent "):
                parents.append(line.removeprefix(b"parent ").decode("ascii"))
        message = b"\n".join(lines)
        return cls(parents=tuple(parents), message=message)


@cache
def git_dir() -> Path:
    for p in path_and_parents(Path.cwd()):
        d = p / ".git"
        if d.is_dir():
            return d
    raise Exception("not a git repository (or any of the parent directories): .git")


@cache
def config() -> Config:
    config_file = git_dir() / "config"
    return parse_config(config_file.open())


@cache
def git_head() -> str:
    return (git_dir() / "HEAD").open(encoding="utf-8").read().strip()


class Commit:
    def __init__(self, hash: str):
        self.hash = hash
        self._cached_git_object: GitObject | None = None

    @property
    def parents(self) -> "tuple[Commit, ...]":
        return tuple(Commit(hash) for hash in self._git_object().parents)

    @property
    def first_parent(self) -> "Commit | None":
        hash = self._git_object().first_parent
        return Commit(hash) if hash else None

    @property
    def message(self) -> bytes:
        return self._git_object().message

    def _git_object(self) -> GitObject:
        if self._cached_git_object is None:
            # TODO: Handle packfiles
            filename = git_dir() / "objects" / self.hash[:2] / self.hash[2:]
            with open(filename, "rb") as f:
                self._cached_git_object = GitObject.decode(f)
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


def branches() -> Iterable[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
