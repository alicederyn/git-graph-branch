"""The check status of the open PRs for a branch (ADR 5)."""

import asyncio
from collections.abc import Mapping
from enum import Enum
from typing import Any

from ..git.branch import Branch, RemoteBranch
from .common import Outcome, combine_outcomes, get
from .loader import Fetch, Pending, Result, load
from .remote import github_repository


class CheckStatus(Enum):
    """In order of precedence, when the statuses of several PRs combine."""

    FAILED = "❌"
    LOADING = "🔌"
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
    ref(qualifiedName: $ref) {
      associatedPullRequests(states: OPEN, first: 1) {
        nodes {
          baseRepository {
            defaultBranchRef {
              target { ... on Commit { statusCheckRollup { state } } }
            }
          }
          commits(last: 1) {
            nodes { commit { statusCheckRollup { state } } }
          }
        }
      }
    }
  }
}
"""


def base_repository_has_checks(data: dict[str, Any]) -> bool:
    """Whether the default branch of the PR's base repository has checks.

    Not the repository of the branch: GitHub keeps checks per repository, and CI
    on a fork usually does not run, even on the same commit.
    """
    return (
        get(
            data,
            *("repository", "ref", "associatedPullRequests", "nodes", 0),
            *("baseRepository", "defaultBranchRef", "target", "statusCheckRollup"),
        )
        is not None
    )


def pr_rollup_state(data: dict[str, Any]) -> str | None:
    return get(  # type: ignore[no-any-return]
        data,
        *("repository", "ref", "associatedPullRequests", "nodes", 0),
        *("commits", "nodes", 0, "commit", "statusCheckRollup", "state"),
    )


def check_outcome(result: Result[dict[str, Any]] | Pending) -> Outcome[CheckStatus]:
    """The check status, and whether the latest load failed.

    A rollup state that GitHub adds later is not known, and counts as a failure.
    """
    if result is Pending.PENDING:
        return Outcome(CheckStatus.LOADING)
    state = pr_rollup_state(result.state) if result.state is not None else None
    unknown = state is not None and state not in ROLLUP_STATUS
    status = ROLLUP_STATUS.get(state) if state else None
    return Outcome(status, result.error is not None or unknown)


def poll_interval(result: Result[dict[str, Any]], age: float) -> float:
    """Poll fast just after a push from this machine, when CI is likely to start.

    If the PR's base repository has no checks on its default branch, or there is
    no PR, poll slowly, as CI may never start.
    """
    data = result.state
    if result.error is not None or data is None:
        return MEDIUM_INTERVAL
    if not base_repository_has_checks(data):
        return SLOW_INTERVAL
    if age < FAST_PERIOD:
        return FAST_INTERVAL
    if ROLLUP_STATUS.get(pr_rollup_state(data) or "") == CheckStatus.PENDING:
        return MEDIUM_INTERVAL
    return SLOW_INTERVAL


async def load_pr_checks(
    fetch: Fetch, previous: Mapping[str, Any] | None, owner: str, name: str, ref: str
) -> dict[str, Any]:
    return await fetch(PR_CHECKS_QUERY, {"owner": owner, "name": name, "ref": ref})


async def remote_branch_check_status(
    remote: RemoteBranch, *, wait: bool
) -> Outcome[CheckStatus]:
    found = github_repository(remote.remote)
    if found is None:
        return Outcome()
    github, repository = found
    result = await load(
        github,
        load_pr_checks,
        (repository.owner, repository.name, f"refs/heads/{remote.name}"),
        poll_interval,
        # A push from this machine updates the remote-tracking ref, so load again
        version=remote.commit.hash,
        wait=wait,
    )
    return check_outcome(result)


async def pr_check_status(branch: Branch, *, wait: bool) -> Outcome[CheckStatus]:
    """The combined check status of the open PRs of the branch's remote branches.

    If wait is false, a status that has not loaded is LOADING.
    """
    remotes = {
        r for r in (branch.upstream, branch.downstream) if isinstance(r, RemoteBranch)
    }
    outcomes = await asyncio.gather(
        *(remote_branch_check_status(r, wait=wait) for r in remotes)
    )
    return combine_outcomes(outcomes)
