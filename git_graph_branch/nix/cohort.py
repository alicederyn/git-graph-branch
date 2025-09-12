from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Glob:
    base_path: Path
    pattern: str
    case_sensitive: bool | None


@dataclass
class Cohort:
    paths: set[Path] = field(default_factory=set)
    """Paths interacted with in this cohort (associated files may not exist)."""

    globs: set[Glob] = field(default_factory=set)
    """Globs executed in this cohort."""

    seen: set[Path] = field(default_factory=set)
    """Files seen in the filesystem in this cohort.

    Used to track file deletion.
    """

    on_nix: list[Callable[[], object]] = field(default_factory=list)
    """Callbacks to trigger when a file changes.

    Used to nix invalidated calculations. Called in reverse order.
    """

    def __hash__(self) -> int:
        return id(self)

    def nix(self) -> None:
        """Trigger all nix callbacks."""
        to_call = self.on_nix[::-1]
        self.on_nix.clear()  # Ensure we don't accidentally call anything twice
        for nixer in to_call:
            nixer()


active_cohort: ContextVar[Cohort | None] = ContextVar("active_cohorts", default=None)
on_add_cohort: list[Callable[[Cohort], None]] = []


@contextmanager
def live_cohort_context(cohort: Cohort) -> Iterator[None]:
    for callable in on_add_cohort:
        callable(cohort)
    token = active_cohort.set(cohort)
    try:
        yield
    finally:
        active_cohort.reset(token)
