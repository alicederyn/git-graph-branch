"""The check status of the open PR for a branch (ADR 5)."""

from collections.abc import Mapping
from enum import Enum
from typing import Any

from ..git.branch import Branch
from .common import Outcome, get
from .loader import Fetch, Pending, Result, load
from .remote import Repository, github_repository, new_pr_url, pr_remote_branch


class CheckStatus(Enum):
    FAILED = "❌"
    LOADING = "🔌"
    PENDING = "⌛"
    PASSED = ""


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
    defaultBranchRef { name }
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


def pr(data: dict[str, Any]) -> dict[str, Any] | None:
    return get(data, "repository", "ref", "associatedPullRequests", "nodes", 0)  # type: ignore[no-any-return]


def pr_rollup(pr: dict[str, Any]) -> dict[str, Any] | None:
    return get(pr, "commits", "nodes", 0, "commit", "statusCheckRollup")  # type: ignore[no-any-return]


def pr_rollup_state(data: dict[str, Any]) -> str | None:
    pr_node = pr(data)
    rollup = pr_rollup(pr_node) if pr_node else None
    return rollup["state"] if rollup else None


def new_pr_link(
    data: dict[str, Any], repository: Repository, branch: str
) -> str | None:
    """The link to create a PR, unless the branch is the repository's default
    branch, as GitHub does not show it then."""
    if get(data, "repository", "ref") is None:
        return None
    if get(data, "repository", "defaultBranchRef", "name") == branch:
        return None
    return new_pr_url(repository, branch)


def check_outcome(
    result: Result[dict[str, Any]] | Pending, repository: Repository, branch: str
) -> Outcome[CheckStatus]:
    """The check status of the PR for a remote branch.

    With no PR, the URL is the link to create one. A rollup state that GitHub
    adds later is not known, and counts as a failure.
    """
    if result is Pending.PENDING:
        return Outcome(CheckStatus.LOADING)
    failed = result.error is not None
    data = result.state
    if data is None:
        return Outcome(failed=failed)
    pr_node = pr(data)
    if pr_node is None:
        return Outcome(
            failed=failed, url=new_pr_link(data, repository, branch), has_pr=False
        )
    state = pr_rollup_state(data)
    unknown = state is not None and state not in ROLLUP_STATUS
    status = ROLLUP_STATUS.get(state) if state else None
    return Outcome(status, failed or unknown, has_pr=True)


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


async def pr_check_status(branch: Branch, *, wait: bool) -> Outcome[CheckStatus]:
    """The check status of the branch's open PR.

    If wait is false, a status that has not loaded is LOADING.
    """
    remote = pr_remote_branch(branch)
    if remote is None:
        return Outcome()
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
    return check_outcome(result, repository, remote.name)
