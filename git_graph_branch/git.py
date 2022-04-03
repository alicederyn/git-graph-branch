import re
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
            if m := KEY_VALUE.match(line):
                current_dict[m.group(1)] = m.group(2)
            elif m := KEY_QUOTED_VALUE.match(line):
                current_dict[m.group(1)] = (
                    m.group(2).encode("utf-8").decode("unicode_escape")
                )
            else:
                raise Exception("Error parsing .git/config\nUnexpected line: " + line)
        else:
            raise Exception("Error parsing .git/config\nUnexpected line: " + line)

    return result


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


class Branch:
    def __init__(self, ref: Path | str):
        self._ref = ref if isinstance(ref, Path) else git_dir() / "refs" / "heads" / ref
        # Used frequently enough to eagerly cache
        self.name = self._ref.relative_to(git_dir() / "refs" / "heads").as_posix()

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"git.Branch({repr(self.name)})"

    @property
    def is_head(self) -> bool:
        return git_head() == f"ref: refs/heads/{self.name}"


def branches() -> Iterable[Branch]:
    heads_dir = git_dir() / "refs" / "heads"
    for p in Path.rglob(heads_dir, "*"):
        if p.is_file():
            yield Branch(p)
