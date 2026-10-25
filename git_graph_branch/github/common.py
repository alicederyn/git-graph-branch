"""Helpers shared by the GitHub status modules."""

from enum import Enum
from typing import Any, NamedTuple


def get(data: Any, *path: str | int) -> Any:
    """Follow path through nested JSON, stopping at the first null or missing value."""
    for step in path:
        if data is None:
            return None
        if isinstance(step, int):
            data = data[step] if step < len(data) else None
        else:
            data = data.get(step)
    return data


class Outcome[E: Enum](NamedTuple):
    status: E | None = None
    """The status from the last load that did not fail."""
    failed: bool = False
    """Whether the latest load failed."""


def combine[E: Enum](statuses: list[E | None]) -> E | None:
    """The status that comes first in its enum."""
    known = [status for status in statuses if status is not None]
    if not known:
        return None
    order = list(type(known[0]))
    return min(known, key=order.index)


def combine_outcomes[E: Enum](outcomes: list[Outcome[E]]) -> Outcome[E]:
    return Outcome(
        combine([o.status for o in outcomes]), any(o.failed for o in outcomes)
    )
