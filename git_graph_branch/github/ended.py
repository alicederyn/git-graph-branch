"""The merged or closed PR of a branch that has no open PR."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ..git.branch import Branch
from ..graphql.loader import Fetch, Pending, Result, load
from .checks import MEDIUM_INTERVAL, SLOW_INTERVAL
from .common import Outcome, error_text, get
from .remote import github_push_target


class EndedState(Enum):
    MERGED = "🌸"
    CLOSED = "🪦"


TOOLTIP = {EndedState.MERGED: "PR merged", EndedState.CLOSED: "PR closed"}

CLOCK_SKEW = 60
"""Seconds that a commit date can be wrong by, as clocks on machines differ."""
CANDIDATES_PAGE_SIZE = 5
FIRST_COMMITS_PAGE_SIZE = 10
COMMITS_PAGE_SIZE = 100

CANDIDATES_FRAGMENT = """
fragment Candidates on PullRequestConnection {
  pageInfo { hasNextPage endCursor }
  nodes {
    id state url updatedAt headRefOid
    headRepository { nameWithOwner }
    commits(last: $commits) {
      pageInfo { hasPreviousPage startCursor }
      nodes { commit { oid committedDate } }
    }
  }
}
"""

CANDIDATES = """
pullRequests(
  headRefName: $branch
  states: [MERGED, CLOSED]
  first: $first
  after: $after
  orderBy: { field: UPDATED_AT, direction: DESC }
) { ...Candidates }
"""

ENDED_PRS_QUERY = (
    """
query ($owner: String!, $name: String!, $branch: String!, $first: Int!, $after: String, $commits: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    CANDIDATES
    parent { owner { login } name CANDIDATES }
  }
}
""".replace("CANDIDATES", CANDIDATES)
    + CANDIDATES_FRAGMENT
)

CANDIDATES_PAGE_QUERY = (
    """
query ($owner: String!, $name: String!, $branch: String!, $first: Int!, $after: String, $commits: Int!) {
  repository(owner: $owner, name: $name) { CANDIDATES }
}
""".replace("CANDIDATES", CANDIDATES)
    + CANDIDATES_FRAGMENT
)

COMMITS_PAGE_QUERY = """
query ($pr: ID!, $last: Int!, $before: String) {
  node(id: $pr) {
    ... on PullRequest {
      commits(last: $last, before: $before) {
        pageInfo { hasPreviousPage startCursor }
        nodes { commit { oid committedDate } }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class EndedPr:
    state: EndedState
    url: str
    head_oid: str


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


async def candidates_since(
    fetch: Fetch,
    base: tuple[str, str],
    branch: str,
    page: dict[str, Any],
    since: float,
) -> list[dict[str, Any]]:
    """The PRs of the page, and of the pages after it, updated since the given time."""
    candidates: list[dict[str, Any]] = []
    while True:
        for node in page["nodes"]:
            if timestamp(node["updatedAt"]) < since:
                return candidates
            candidates.append(node)
        if not page["pageInfo"]["hasNextPage"]:
            return candidates
        data = await fetch(
            CANDIDATES_PAGE_QUERY,
            {
                "owner": base[0],
                "name": base[1],
                "branch": branch,
                "first": CANDIDATES_PAGE_SIZE,
                "after": page["pageInfo"]["endCursor"],
                "commits": FIRST_COMMITS_PAGE_SIZE,
            },
        )
        page = data["repository"]["pullRequests"]


async def contains_commit(
    fetch: Fetch, pr: dict[str, Any], oid: str, since: float
) -> bool:
    """Whether the PR's commits include oid.

    Walks back from the head, and stops at a commit older than since. The commits
    after oid descend from it, and a rebase, cherry-pick or commit on GitHub gives
    a commit a new committer date, so they are not older.
    """
    page = pr["commits"]
    while True:
        for node in reversed(page["nodes"]):
            commit = node["commit"]
            if commit["oid"] == oid:
                return True
            if timestamp(commit["committedDate"]) < since:
                return False
        if not page["pageInfo"]["hasPreviousPage"]:
            return False
        data = await fetch(
            COMMITS_PAGE_QUERY,
            {
                "pr": pr["id"],
                "last": COMMITS_PAGE_SIZE,
                "before": page["pageInfo"]["startCursor"],
            },
        )
        page = data["node"]["commits"]


async def load_ended_prs(
    fetch: Fetch,
    previous: tuple[EndedPr, ...] | None,
    commit: tuple[str, int] | None,
    owner: str,
    name: str,
    branch: str,
) -> tuple[EndedPr, ...]:
    """The merged and closed PRs from the branch whose commits include the commit,
    most recently updated first.

    The commit is the oid and committer time of the remote-tracking branch, or
    None if there is no remote-tracking branch.

    A PR from a fork is in the fork's parent. A PR from another fork, with the same
    branch name, is not the branch's PR.
    """
    if commit is None:
        return ()
    oid, committed_at = commit
    data = await fetch(
        ENDED_PRS_QUERY,
        {
            "owner": owner,
            "name": name,
            "branch": branch,
            "first": CANDIDATES_PAGE_SIZE,
            "after": None,
            "commits": FIRST_COMMITS_PAGE_SIZE,
        },
    )
    repository = data["repository"]
    if repository is None:
        return ()
    # A commit is pushed after it is committed, so a PR that holds it is updated after
    since = committed_at - CLOCK_SKEW
    bases = [((owner, name), repository["pullRequests"])]
    if parent := repository["parent"]:
        bases.append(
            ((parent["owner"]["login"], parent["name"]), parent["pullRequests"])
        )
    pages = await asyncio.gather(
        *(candidates_since(fetch, base, branch, page, since) for base, page in bases)
    )
    candidates = [
        pr
        for page in pages
        for pr in page
        if get(pr, "headRepository", "nameWithOwner") == repository["nameWithOwner"]
    ]
    found = await asyncio.gather(
        *(contains_commit(fetch, pr, oid, since) for pr in candidates)
    )
    matches = sorted(
        (pr for pr, contains in zip(candidates, found) if contains),
        key=lambda pr: timestamp(pr["updatedAt"]),
        reverse=True,
    )
    return tuple(
        EndedPr(EndedState[pr["state"]], pr["url"], pr["headRefOid"]) for pr in matches
    )


def ended_outcome(
    result: Result[tuple[EndedPr, ...]] | Pending, remote_oid: str | None
) -> Outcome[EndedState]:
    """The most recently updated PR, unless commits were pushed after it ended.

    remote_oid is the commit of the branch on GitHub, or None if GitHub deleted it.
    """
    if result is Pending.PENDING:
        return Outcome(loading=True)
    error = error_text(result.error)
    pr = next(
        (
            pr
            for pr in result.state or ()
            if remote_oid is None or remote_oid == pr.head_oid
        ),
        None,
    )
    if pr is None:
        return Outcome(error=error)
    return Outcome(pr.state, error, pr.url, tooltip=TOOLTIP[pr.state])


def agreeing(
    result: Result[tuple[EndedPr, ...]] | Pending, commit: tuple[str, int] | None
) -> Result[tuple[EndedPr, ...]] | Pending:
    """result, changed to agree with the commit of the remote-tracking branch.

    With no remote-tracking branch, the branch has no PR. After a push, the
    outcome hides the PRs whose head is not the new commit.
    """
    if result is Pending.PENDING or commit is not None or result.input is None:
        return result
    return Result((), result.error, None)


def poll_interval(result: Result[tuple[EndedPr, ...]], age: float) -> float:
    """Poll slowly, as a PR that has ended stays ended, and a new open PR shows in
    the check status."""
    return MEDIUM_INTERVAL if result.error is not None else SLOW_INTERVAL


async def pr_ended_status(
    branch: Branch, remote_oid: str | None, *, wait: bool
) -> Outcome[EndedState]:
    """The merged or closed PR of the branch.

    Call only if the branch has no open PR. remote_oid is the commit of the branch
    on GitHub, or None if GitHub deleted it. If wait is false, a status that has
    not loaded is loading.
    """
    target = github_push_target(branch)
    if target is None:
        return Outcome()
    repository = target.repository
    tracking = target.tracking
    commit = (tracking.commit.hash, tracking.commit.commit_date) if tracking else None
    result = await load(
        target.endpoint,
        load_ended_prs,
        (repository.owner, repository.name, target.name),
        poll_interval,
        input=commit,
        wait=wait,
    )
    return ended_outcome(agreeing(result, commit), remote_oid)
