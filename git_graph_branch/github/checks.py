"""The check status of the open PR for a branch (ADR 5)."""

from collections.abc import Mapping
from enum import Enum
from typing import Any

from ..git.branch import Branch
from ..graphql.loader import Fetch, Pending, Result, load
from .common import Outcome, error_text, get
from .remote import Repository, new_pr_url, status_branch


class CheckStatus(Enum):
    FAILED = "❌"
    PENDING = "⌛"
    PASSED = ""


ROLLUP_STATUS = {
    "FAILURE": CheckStatus.FAILED,
    "ERROR": CheckStatus.FAILED,
    "PENDING": CheckStatus.PENDING,
    "EXPECTED": CheckStatus.PENDING,
    "SUCCESS": CheckStatus.PASSED,
}

NOT_ON_GITHUB: dict[str, Any] = {"repository": {"defaultBranchRef": None, "ref": None}}
"""The state of a branch that is not on GitHub, in a repository whose default
branch is not known."""

FAST_INTERVAL = 5.0
FAST_PERIOD = 180.0
MEDIUM_INTERVAL = 30.0
SLOW_INTERVAL = 300.0

PR_CHECKS_QUERY = """
query ($owner: String!, $name: String!, $ref: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name }
    ref(qualifiedName: $ref) {
      target { oid }
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


def remote_reason(data: dict[str, Any], remote: str, local_oid: str) -> str | None:
    """Why the remote-tracking branch is not the same as the branch on GitHub."""
    if get(data, "repository") is None:
        return None
    oid = get(data, "repository", "ref", "target", "oid")
    if oid is None:
        return f"{remote}: deleted on remote"
    if oid != local_oid:
        return f"{remote}: changed on remote"
    return None


def check_outcome(
    result: Result[dict[str, Any]] | Pending,
    repository: Repository,
    branch: str,
    remote: str,
    local_oid: str,
) -> Outcome[CheckStatus]:
    """The check status of the PR for a remote branch.

    With no PR, the URL is the link to create one. A rollup state that GitHub
    adds later is not known, and counts as a failure. The remote reason says if
    local_oid, the commit of the remote-tracking branch, is out of date.
    """
    if result is Pending.PENDING:
        return Outcome(loading=True)
    error = error_text(result.error)
    data = result.state
    if data is None:
        return Outcome(error=error)
    oid = get(data, "repository", "ref", "target", "oid")
    reason = remote_reason(data, remote, local_oid)
    pr_node = pr(data)
    if pr_node is None:
        return Outcome(
            error=error,
            url=new_pr_link(data, repository, branch),
            has_pr=False,
            remote_oid=oid,
            remote_reason=reason,
        )
    state = pr_rollup_state(data)
    if error is None and state is not None and state not in ROLLUP_STATUS:
        error = f"Unknown check state {state}"
    status = ROLLUP_STATUS.get(state) if state else None
    return Outcome(status, error, has_pr=True, remote_oid=oid, remote_reason=reason)


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


def after_push(data: dict[str, Any], oid: str) -> dict[str, Any]:
    """data, changed to agree with a push of oid from this machine.

    GitHub accepted the push, so the branch exists at oid. A push does not reopen
    a PR, so a branch that was deleted, or not on GitHub, has no open PR.
    """
    repository = data.get("repository")
    if repository is None:
        return data
    ref = repository.get("ref") or {"associatedPullRequests": {"nodes": []}}
    return {
        **data,
        "repository": {**repository, "ref": {**ref, "target": {"oid": oid}}},
    }


def agreeing(
    result: Result[dict[str, Any]] | Pending, oid: str, first_push: bool
) -> Result[dict[str, Any]] | Pending:
    """result, changed to agree with oid, the commit of the remote-tracking branch.

    A result that was loaded for another commit is older than oid, as git changes
    the remote-tracking branch after GitHub accepts a push. After a first push,
    a pending result is a branch at oid with no PR.
    """
    if result is Pending.PENDING:
        if first_push:
            return Result(after_push(NOT_ON_GITHUB, oid), None, oid)
        return result
    if result.state is None or result.input == oid:
        return result
    return Result(after_push(result.state, oid), result.error, oid)


async def load_pr_checks(
    fetch: Fetch,
    previous: Mapping[str, Any] | None,
    oid: str,
    owner: str,
    name: str,
    ref: str,
) -> dict[str, Any]:
    return await fetch(PR_CHECKS_QUERY, {"owner": owner, "name": name, "ref": ref})


async def pr_check_status(branch: Branch, *, wait: bool) -> Outcome[CheckStatus]:
    """The check status of the branch's open PR.

    If wait is false, a status that has not loaded is loading.
    """
    source = status_branch(branch)
    if source is None:
        return Outcome(has_pr=False)
    repository = source.repository
    result = await load(
        source.endpoint,
        load_pr_checks,
        (repository.owner, repository.name, source.ref),
        poll_interval,
        # A push from this machine updates the remote-tracking ref, so load again
        input=source.oid,
        wait=wait,
    )
    return check_outcome(
        agreeing(
            result,
            source.oid,
            source.assumes_no_pr(load_pr_checks, result is Pending.PENDING),
        ),
        repository,
        source.remote.name,
        source.remote.remote,
        source.oid,
    )
