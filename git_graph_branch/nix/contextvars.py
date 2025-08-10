from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .cohort import Cohort, Nixer

active_cohort: ContextVar[Cohort | None] = ContextVar("_cohort_var", default=None)
active_nixer: ContextVar[Nixer | None] = ContextVar("_nixer_var", default=None)


@contextmanager
def live_cohort_context(cohort: Cohort) -> Iterator[None]:
    _nixer = active_nixer.get()
    if not _nixer:
        raise RuntimeError("No active nixer")
    if cohort in _nixer.cohorts:
        raise RuntimeError("Cannot register cohort twice")
    _nixer.add_cohort(cohort)
    token = active_cohort.set(cohort)
    try:
        yield
    finally:
        _nixer.remove_cohort(cohort)
        active_cohort.reset(token)


@contextmanager
def live_nixer(nixer: Nixer) -> Iterator[None]:
    token = active_nixer.set(nixer)
    try:
        yield
    finally:
        active_nixer.reset(token)
