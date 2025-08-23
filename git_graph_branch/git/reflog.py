from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .commit import Commit
from .file_algos import readlines_reversed


@dataclass(frozen=True)
class ReflogEntry:
    commit: Commit
    timestamp: int


def reflog_from_line(line: str) -> ReflogEntry:
    hash = line[41:81]
    end_of_user_address = line.find(">", 81)
    unix_time = line[end_of_user_address + 2 :].split(" ", 1)[0]

    return ReflogEntry(Commit(hash), int(unix_time))


def iter_reflog(path: Path) -> Iterator[ReflogEntry]:
    return (reflog_from_line(line) for line in readlines_reversed(path))
