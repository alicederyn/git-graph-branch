"""The review status of the open PRs for a branch (ADR 7)."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import aiohttp

from ..git.branch import Branch, RemoteBranch
from .common import Outcome, combine_outcomes, get
from .loader import Fetch, Pending, Result, load
from .remote import github_repository


class ReviewStatus(Enum):
    """In order of precedence, when the statuses of several PRs combine."""

    CHANGES_REQUESTED = "👎"
    AWAITING_DISMISSAL = "🚧"
    COMMENTED = "💬"
    APPROVED = "👍"
    OPEN = "📭"


POLL_INTERVAL = 300.0
RETRY_INTERVAL = 30.0
MAX_PAGE_SIZE = 100
MIN_THREADS_PAGE_SIZE = 10
THREADS_MARGIN = 5


@dataclass(frozen=True)
class Connection:
    """A connection of a PullRequest, as a fragment.

    The fragment pages with the variables $<name>First and $<name>After, so that
    one query can hold the first page of each connection.
    """

    name: str
    field: str
    items: str
    fragment: str

    @property
    def fragment_name(self) -> str:
        return self.fragment.split()[1]

    @property
    def variable_definitions(self) -> str:
        return f"${self.name}First: Int!, ${self.name}After: String"

    def variables(self, first: int, after: str | None) -> dict[str, Any]:
        return {f"{self.name}First": first, f"{self.name}After": after}

    @property
    def page_query(self) -> str:
        return (
            f"query ($pr: ID!, {self.variable_definitions}) {{"
            f" node(id: $pr) {{ ...{self.fragment_name} }} }}\n" + self.fragment
        )


OPINIONATED_REVIEWS = Connection(
    "opinionated",
    "latestOpinionatedReviews",
    "nodes",
    """
fragment OpinionatedReviews on PullRequest {
  latestOpinionatedReviews(first: $opinionatedFirst, after: $opinionatedAfter) {
    pageInfo { hasNextPage endCursor }
    nodes { state submittedAt author { login } }
  }
}
""",
)
REVIEW_REQUESTS = Connection(
    "requests",
    "reviewRequests",
    "nodes",
    """
fragment ReviewRequests on PullRequest {
  reviewRequests(first: $requestsFirst, after: $requestsAfter) {
    pageInfo { hasNextPage endCursor }
    nodes { requestedReviewer { ... on User { login } } }
  }
}
""",
)
REVIEW_REQUEST_EVENTS = Connection(
    "events",
    "timelineItems",
    "nodes",
    """
fragment ReviewRequestEvents on PullRequest {
  timelineItems(
    itemTypes: [REVIEW_REQUESTED_EVENT], first: $eventsFirst, after: $eventsAfter
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on ReviewRequestedEvent { createdAt requestedReviewer { ... on User { login } } }
    }
  }
}
""",
)
# Each thread also costs a request for its first comment, so the page size of
# threads is the main cost of the query
REVIEW_THREADS = Connection(
    "threads",
    "reviewThreads",
    "edges",
    """
fragment ReviewThreads on PullRequest {
  reviewThreads(first: $threadsFirst, after: $threadsAfter) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      cursor
      node {
        isResolved
        comments(first: 1) {
          nodes { pullRequestReview { state submittedAt author { login } } }
        }
      }
    }
  }
}
""",
)
REVIEW_CONNECTIONS = [OPINIONATED_REVIEWS, REVIEW_REQUESTS, REVIEW_REQUEST_EVENTS]
FIRST_PAGES = [*REVIEW_CONNECTIONS, REVIEW_THREADS]

PR_REVIEWS_QUERY = (
    """
query ($owner: String!, $name: String!, $ref: String!, VARIABLES) {
  repository(owner: $owner, name: $name) {
    ref(qualifiedName: $ref) {
      associatedPullRequests(states: OPEN, first: 1) {
        nodes { id reviewDecision SPREADS }
      }
    }
  }
}
""".replace(
        "VARIABLES", ", ".join(c.variable_definitions for c in FIRST_PAGES)
    ).replace("SPREADS", " ".join("..." + c.fragment_name for c in FIRST_PAGES))
    + "".join(c.fragment for c in FIRST_PAGES)
)


@dataclass(frozen=True)
class Review:
    author: str | None
    state: str
    submitted_at: datetime | None


@dataclass(frozen=True)
class Reviews:
    pr_id: str | None
    """None if the branch has no open PR."""
    decision: str | None = None
    opinionated: tuple[Review, ...] = ()
    """The latest approval or change request of each user."""
    requested: frozenset[str] = frozenset()
    """Users with a pending review request."""
    requested_at: tuple[tuple[str, datetime], ...] = ()
    """When each user was asked for a review, oldest first."""
    unresolved: frozenset[Review] = frozenset()
    """The reviews that started the unresolved threads."""
    threads_cursor: str | None = None
    """Where the next load starts to read threads."""
    threads_before: int = 0
    """How many threads come before threads_cursor."""
    threads_after: int = 0
    """How many threads came after threads_cursor."""


NO_PR = Reviews(pr_id=None)


def author(node: dict[str, Any]) -> str | None:
    return get(node, "author", "login")  # type: ignore[no-any-return]


def timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def page_size(remaining: int) -> int:
    return max(1, min(MAX_PAGE_SIZE, remaining))


async def next_page(
    fetch: Fetch, pr_id: str, connection: Connection, after: str | None, first: int
) -> dict[str, Any]:
    data = await fetch(
        connection.page_query, {"pr": pr_id, **connection.variables(first, after)}
    )
    return data["node"][connection.field]  # type: ignore[no-any-return]


async def rest_of_connection(
    fetch: Fetch,
    pr_id: str,
    connection: Connection,
    page: dict[str, Any],
    remaining: int = MAX_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """The items of the page, and of all pages after it.

    remaining is an estimate of how many items there are, to size the next pages.
    """
    items = list(page[connection.items])
    while page["pageInfo"]["hasNextPage"]:
        page = await next_page(
            fetch,
            pr_id,
            connection,
            page["pageInfo"]["endCursor"],
            page_size(remaining - len(items)),
        )
        items.extend(page[connection.items])
    return items


def first_threads_page_size(previous: Reviews) -> int:
    """Enough for the threads that came after the cursor last time, and a few more."""
    return max(
        MIN_THREADS_PAGE_SIZE, page_size(previous.threads_after + THREADS_MARGIN)
    )


def first_page_variables(previous: Reviews) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for connection in REVIEW_CONNECTIONS:
        variables |= connection.variables(MAX_PAGE_SIZE, None)
    variables |= REVIEW_THREADS.variables(
        first_threads_page_size(previous), previous.threads_cursor
    )
    return variables


def resolved_prefix(edges: list[dict[str, Any]]) -> int:
    """How many threads come before the first unresolved thread.

    Assumes that resolved threads stay resolved, so the next load can skip them.
    """
    for index, edge in enumerate(edges):
        if not edge["node"]["isResolved"]:
            return index
    return len(edges)


def review(node: dict[str, Any]) -> Review:
    return Review(author(node), node["state"], timestamp(node["submittedAt"]))


def first_review(thread: dict[str, Any]) -> Review | None:
    node = get(thread, "comments", "nodes", 0, "pullRequestReview")
    return review(node) if node else None


async def load_pr_reviews(
    fetch: Fetch, previous: Reviews | None, owner: str, name: str, ref: str
) -> Reviews:
    previous = previous or NO_PR
    data = await fetch(
        PR_REVIEWS_QUERY,
        {"owner": owner, "name": name, "ref": ref, **first_page_variables(previous)},
    )
    pr = get(data, "repository", "ref", "associatedPullRequests", "nodes", 0)
    if pr is None:
        return NO_PR
    pr_id = pr["id"]
    threads_page = pr[REVIEW_THREADS.field]
    total = threads_page["totalCount"]
    if previous.threads_cursor is not None and previous.pr_id != pr_id:
        # The cursor is from another PR
        previous = NO_PR
        threads_page = await next_page(
            fetch, pr_id, REVIEW_THREADS, None, page_size(total)
        )
    opinionated, requests, events, threads = await asyncio.gather(
        *(rest_of_connection(fetch, pr_id, c, pr[c.field]) for c in REVIEW_CONNECTIONS),
        rest_of_connection(
            fetch, pr_id, REVIEW_THREADS, threads_page, total - previous.threads_before
        ),
    )
    skipped = resolved_prefix(threads)
    return Reviews(
        pr_id=pr_id,
        decision=pr["reviewDecision"],
        opinionated=tuple(review(node) for node in opinionated),
        requested=frozenset(
            login
            for node in requests
            if (login := get(node, "requestedReviewer", "login"))
        ),
        requested_at=tuple(
            (login, datetime.fromisoformat(node["createdAt"]))
            for node in events
            if (login := get(node, "requestedReviewer", "login"))
        ),
        unresolved=frozenset(
            thread_review
            for edge in threads
            if not edge["node"]["isResolved"]
            and (thread_review := first_review(edge["node"]))
        ),
        threads_cursor=threads[skipped - 1]["cursor"]
        if skipped
        else previous.threads_cursor,
        threads_before=previous.threads_before + skipped,
        threads_after=len(threads) - skipped,
    )


def is_approved(reviews: Reviews, current: list[Review]) -> bool:
    """Whether GitHub's review rules allow merge, and no approver is asked again.

    GitHub keeps an approval when its author is asked for a review again. With no
    review rules, reviewDecision is null.
    """
    if reviews.decision == "APPROVED":
        return not any(
            r.state == "APPROVED" and r.author in reviews.requested
            for r in reviews.opinionated
        )
    return (
        reviews.decision is None
        and any(r.state == "APPROVED" for r in current)
        and not any(r.state == "CHANGES_REQUESTED" for r in current)
    )


def is_awaiting_dismissal(reviews: Reviews, current: list[Review]) -> bool:
    """Whether each change request is asked again, and approved by another user
    since then.

    GitHub keeps a change request when its author is asked for a review again,
    so the PR stays blocked until the review is dismissed.
    """
    if reviews.decision != "CHANGES_REQUESTED":
        return False
    requested_at = dict(reviews.requested_at)
    blockers = [r for r in reviews.opinionated if r.state == "CHANGES_REQUESTED"]

    def approved_since_request(blocker: Review) -> bool:
        asked = requested_at.get(blocker.author) if blocker.author else None
        return asked is not None and any(
            r.state == "APPROVED"
            and r.author != blocker.author
            and r.submitted_at is not None
            and r.submitted_at > asked
            for r in current
        )

    return bool(blockers) and all(
        b.author in reviews.requested and approved_since_request(b) for b in blockers
    )


def has_unresolved_comments(reviews: Reviews) -> bool:
    """Whether a comment-only review has an unresolved thread.

    A later approval or dismissal from the same reviewer clears the thread, but a
    later comment-only review does not.
    """
    cleared_at = {
        r.author: r.submitted_at
        for r in reviews.opinionated
        if r.state in ("APPROVED", "DISMISSED")
    }

    def is_cleared(thread_review: Review) -> bool:
        if thread_review.author not in cleared_at:
            return False
        at = cleared_at[thread_review.author]
        return (
            at is None
            or thread_review.submitted_at is None
            or at > thread_review.submitted_at
        )

    return any(
        r.state == "COMMENTED"
        and r.author not in reviews.requested
        and not is_cleared(r)
        for r in reviews.unresolved
    )


def review_status(reviews: Reviews) -> ReviewStatus | None:
    if reviews.pr_id is None:
        return None
    # A dismissed review has the state DISMISSED
    current = [
        r
        for r in reviews.opinionated
        if r.state != "DISMISSED" and r.author not in reviews.requested
    ]
    if is_approved(reviews, current):
        return ReviewStatus.APPROVED
    if any(r.state == "CHANGES_REQUESTED" for r in current):
        return ReviewStatus.CHANGES_REQUESTED
    if is_awaiting_dismissal(reviews, current):
        return ReviewStatus.AWAITING_DISMISSAL
    if has_unresolved_comments(reviews):
        return ReviewStatus.COMMENTED
    return ReviewStatus.OPEN


def review_outcome(result: Result[Reviews] | Pending) -> Outcome[ReviewStatus]:
    if result is Pending.PENDING:
        return Outcome()
    status = review_status(result.state) if result.state is not None else None
    return Outcome(status, result.error is not None)


def poll_interval(result: Result[Reviews], age: float) -> float:
    """Retry soon after a connection failure, which costs no rate limit."""
    if isinstance(result.error, aiohttp.ClientConnectionError):
        return RETRY_INTERVAL
    return POLL_INTERVAL


async def remote_branch_review_status(
    remote: RemoteBranch, *, wait: bool
) -> Outcome[ReviewStatus]:
    found = github_repository(remote.remote)
    if found is None:
        return Outcome()
    github, repository = found
    result = await load(
        github,
        load_pr_reviews,
        (repository.owner, repository.name, f"refs/heads/{remote.name}"),
        poll_interval,
        wait=wait,
    )
    return review_outcome(result)


async def pr_review_status(branch: Branch, *, wait: bool) -> Outcome[ReviewStatus]:
    """The combined review status of the open PRs of the branch's remote branches.

    If wait is false, a status that has not loaded is None.
    """
    remotes = {
        r for r in (branch.upstream, branch.downstream) if isinstance(r, RemoteBranch)
    }
    outcomes = await asyncio.gather(
        *(remote_branch_review_status(r, wait=wait) for r in remotes)
    )
    return combine_outcomes(outcomes)
