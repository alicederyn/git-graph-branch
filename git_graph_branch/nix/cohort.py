from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol


class Nixer(Protocol):
    def add_cohort(self, cohort: Cohort) -> None: ...
    def path_seen(self, cohort: Cohort, path: Path) -> None: ...
    def remove_cohort(self, cohort: Cohort) -> None: ...
    @property
    def cohorts(self) -> Collection[Cohort]: ...


@dataclass(frozen=True)
class Glob:
    base_path: Path
    pattern: str
    case_sensitive: bool | None


@dataclass
class Cohort:
    nix: Callable[[], None]
    paths: set[Path] = field(default_factory=set)
    globs: set[Glob] = field(default_factory=set)
    invalidate_caches: list[Callable[[], None]] = field(default_factory=list)

    def __hash__(self) -> int:
        return id(self)
