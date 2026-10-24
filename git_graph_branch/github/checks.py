"""The check status of the open PRs for a branch (ADR 5)."""

import asyncio
from enum import Enum
from typing import Any

from ..git.branch import Branch, RemoteBranch
from .loader import Result, query
from .remote import endpoint, remote_repository


class CheckStatus(Enum):
    """In order of precedence, when the statuses of several PRs combine."""

    FAILED = "❌"
    UNKNOWN = "⚠️"
    PENDING = "⌛"
    PASSED = "✅"


ROLLUP_STATUS = {
    "FAILURE": CheckStatus.FAILED,
    "ERROR": CheckStatus.FAILED,
    "PENDING": CheckStatus.PENDING,
    "EXPECTED": CheckStatus.PENDING,
    "SUCCESS": CheckStatus.PASSED,
}

FAST_INTERVAL = 5.0
FAST_PERIOD = 180.0
MEDIUM_INTERVAL = 30.0
SLOW_INTERVAL = 300.0

PR_CHECKS_QUERY = """
query ($owner: String!, $name: String!, $ref: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target { ... on Commit { statusCheckRollup { state } } }
    }
    ref(qualifiedName: $ref) {
      associatedPullRequests(states: OPEN, first: 1) {
        nodes {
          commits(last: 1) {
            nodes { commit { statusCheckRollup { state } } }
          }
        }
      }
    }
  }
}
"""


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


def repository_has_checks(data: dict[str, Any]) -> bool:
    return (
        get(data, "repository", "defaultBranchRef", "target", "statusCheckRollup")
        is not None
    )


def pr_rollup_state(data: dict[str, Any]) -> str | None:
    return get(  # type: ignore[no-any-return]
        data,
        *("repository", "ref", "associatedPullRequests", "nodes", 0),
        *("commits", "nodes", 0, "commit", "statusCheckRollup", "state"),
    )


def check_status(result: Result) -> CheckStatus | None:
    if isinstance(result, Exception):
        return CheckStatus.UNKNOWN
    state = pr_rollup_state(result)
    return ROLLUP_STATUS.get(state, CheckStatus.UNKNOWN) if state else None


def poll_interval(result: Result, age: float) -> float:
    """Poll fast just after a push from this machine, when CI is likely to start.

    In a repository with no checks on the default branch, poll slowly, as CI may
    never start.
    """
    if isinstance(result, Exception):
        return MEDIUM_INTERVAL
    if not repository_has_checks(result):
        return SLOW_INTERVAL
    if age < FAST_PERIOD:
        return FAST_INTERVAL
    if check_status(result) == CheckStatus.PENDING:
        return MEDIUM_INTERVAL
    return SLOW_INTERVAL


async def remote_branch_check_status(remote: RemoteBranch) -> CheckStatus | None:
    repository = remote_repository(remote.remote)
    if repository is None:
        return None
    github = endpoint(repository.domain)
    if github is None:
        return None
    result = await query(
        github,
        PR_CHECKS_QUERY,
        {
            "owner": repository.owner,
            "name": repository.name,
            "ref": f"refs/heads/{remote.name}",
        },
        poll_interval,
        # A push from this machine updates the remote-tracking ref, so load again
        version=remote.commit.hash,
    )
    return check_status(result)


def combine(statuses: list[CheckStatus | None]) -> CheckStatus | None:
    order = list(CheckStatus)
    known = [status for status in statuses if status is not None]
    return min(known, key=order.index) if known else None


async def pr_check_status(branch: Branch) -> CheckStatus | None:
    """The combined check status of the open PRs of the branch's remote branches."""
    remotes = {
        r for r in (branch.upstream, branch.downstream) if isinstance(r, RemoteBranch)
    }
    statuses = await asyncio.gather(*(remote_branch_check_status(r) for r in remotes))
    return combine(statuses)
