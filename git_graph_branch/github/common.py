"""Helpers shared by the GitHub status modules."""

from enum import Enum
from typing import Any, NamedTuple

import aiohttp


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
    error: str | None = None
    """Why the latest load failed, if it did."""
    url: str | None = None
    """Where the status icon links, from the last load that did not fail."""
    has_pr: bool | None = None
    """Whether the branch has an open PR, or None if no load has succeeded.

    False if the branch cannot have one: it has no remote branch on GitHub with
    a token.
    """
    loading: bool = False
    """Whether the status is not loaded yet, as the caller did not wait."""
    tooltip: str | None = None
    """More detail on the status, from the last load that did not fail."""
    remote_oid: str | None = None
    """The commit of the remote branch on GitHub, from the last load that did not
    fail, or None if it does not exist or is not known."""
    remote_reason: str | None = None
    """Why the remote-tracking branch is out of date, if GitHub shows that it is."""


def error_text(error: Exception | None) -> str | None:
    """A short description of error, to fit in a tooltip."""
    if error is None:
        return None
    if isinstance(error, aiohttp.ClientResponseError):
        return f"{error.status} {error.message}"
    return str(error) or type(error).__name__
