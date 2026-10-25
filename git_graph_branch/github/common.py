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
    url: str | None = None
    """Where the status icon links, from the last load that did not fail."""
    has_pr: bool | None = None
    """Whether the branch has an open PR, or None if no load has succeeded.

    False if the branch cannot have one: it has no remote branch on GitHub with
    a token.
    """
    loading: bool = False
    """Whether the status is not loaded yet, as the caller did not wait."""
