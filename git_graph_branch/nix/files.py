"""The fact-finder for file state facts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from stat import S_ISDIR

from .fact import Fact

# Capture Path methods before nix patches them
# Be careful not to capture methods that call other methods
PATH_GLOB = Path.glob
PATH_STAT = Path.stat

SAFETY_MARGIN = timedelta(seconds=1)


def is_dir(path: Path) -> bool:
    """Determine if path is a directory.

    Reimplemented as Path.is_dir calls Path.stat
    """
    try:
        return S_ISDIR(PATH_STAT(path, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False


def exists(path: Path) -> bool:
    try:
        PATH_STAT(path)
        return True
    except FileNotFoundError:
        return False


@dataclass(frozen=True)
class Glob:
    base_path: Path
    pattern: str
    case_sensitive: bool | None


def default_timestamp() -> float:
    return (datetime.now(UTC) - SAFETY_MARGIN).timestamp()


@dataclass(eq=False)
class PathState:
    path: Path
    """Path interacted with (the associated file may not exist)."""

    existed: bool
    """Used to track file deletion."""

    fact: Fact = field(default_factory=Fact)
    timestamp: float = field(default_factory=default_timestamp)

    @property
    def key(self) -> Path:
        return self.path

    def should_nix(self) -> bool:
        try:
            stat = PATH_STAT(self.path)
        except FileNotFoundError:
            return self.existed
        # Created or modified
        return stat.st_mtime >= self.timestamp


@dataclass(eq=False)
class GlobState:
    glob: Glob

    seen: set[Path]
    """Files seen in the filesystem.

    Used to track file deletion.
    """

    fact: Fact = field(default_factory=Fact)
    timestamp: float = field(default_factory=default_timestamp)

    @property
    def key(self) -> Glob:
        return self.glob

    def should_nix(self) -> bool:
        unseen = self.seen.copy()
        glob = self.glob
        for path in PATH_GLOB(
            glob.base_path, glob.pattern, case_sensitive=glob.case_sensitive
        ):
            try:
                stat = PATH_STAT(path)
                unseen.discard(path)
                if stat.st_mtime >= self.timestamp:
                    # Created or modified
                    return True
            except FileNotFoundError:
                pass

        # Any deleted?
        return bool(unseen)


type FileState = PathState | GlobState


file_states: dict[Path | Glob, FileState] = {}
on_add_file_state: list[Callable[[FileState], None]] = []
_watches: set[asyncio.Event] = set()
"""Set when a file state is added or dropped."""


def record_path(path: Path) -> None:
    state = file_states.get(path)
    if state is None:
        state = _add(PathState(path, existed=exists(path)))
    state.fact.record_use()


def record_glob(glob: Glob, results: Iterable[Path]) -> None:
    state = file_states.get(glob)
    if state is None:
        state = _add(GlobState(glob, seen=set(results)))
    state.fact.record_use()


def _add(state: FileState) -> FileState:
    file_states[state.key] = state
    state.fact.on_nix(state.fact.on_moot(_drop, state.key))
    for hook in on_add_file_state:
        hook(state)
    _notify_watches()
    return state


def _drop(key: Path | Glob) -> None:
    del file_states[key]
    _notify_watches()


def _notify_watches() -> None:
    for changed in _watches:
        changed.set()


def nix_changed_file_states() -> None:
    to_nix = [state for state in file_states.values() if state.should_nix()]
    for state in to_nix:
        state.fact.nix()


async def track_file_changes(
    await_changes_and_nix: Callable[[asyncio.Event], Coroutine[None, None, None]],
) -> None:
    """Watch the files of all file state facts.

    Restarts the watch each time the set of file states changes.
    """
    while True:
        changed = asyncio.Event()
        _watches.add(changed)
        try:
            await await_changes_and_nix(changed)
        finally:
            _watches.discard(changed)
