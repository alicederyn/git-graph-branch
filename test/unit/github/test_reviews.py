from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import pytest

from git_graph_branch.github.checks import FAST_INTERVAL
from git_graph_branch.github.common import Outcome
from git_graph_branch.github.loader import Pending, Result
from git_graph_branch.github.reviews import (
    DISMISSAL_PERIOD,
    NO_PR,
    OPINIONATED_REVIEWS,
    POLL_INTERVAL,
    PR_REVIEWS_QUERY,
    RETRY_INTERVAL,
    REVIEW_THREADS,
    Review,
    Reviews,
    ReviewStatus,
    load_pr_reviews,
    poll_interval,
    review_outcome,
    review_status,
    review_tooltip,
)

T0 = datetime(2026, 10, 1)
LATER = T0 + timedelta(hours=1)
PR_URL = "https://github.com/o/n/pull/1"


def opinion(
    author: str, state: str, at: datetime = T0, url: str | None = None
) -> Review:
    return Review(author, state, at, url)


def comment(author: str, at: datetime = T0, url: str | None = None) -> Review:
    return Review(author, "COMMENTED", at, url)


def reviews(
    decision: str | None = None,
    opinionated: tuple[Review, ...] = (),
    requested: frozenset[str] = frozenset(),
    requested_at: tuple[tuple[str, datetime], ...] = (),
    unresolved: tuple[Review, ...] = (),
    draft: bool = False,
) -> Reviews:
    return Reviews(
        "PR",
        PR_URL,
        decision,
        draft,
        opinionated,
        requested,
        requested_at,
        unresolved,
    )


@pytest.mark.parametrize(
    "state, status",
    [
        (
            reviews("APPROVED", (opinion("ann", "APPROVED"),)),
            ReviewStatus.APPROVED,
        ),
        (
            reviews(None, (opinion("ann", "APPROVED"),)),
            ReviewStatus.APPROVED,
        ),
        (
            reviews("CHANGES_REQUESTED", (opinion("bob", "CHANGES_REQUESTED"),)),
            ReviewStatus.CHANGES_REQUESTED,
        ),
        (
            reviews(
                "CHANGES_REQUESTED",
                (
                    opinion("bob", "CHANGES_REQUESTED"),
                    opinion("ann", "APPROVED", LATER),
                ),
                requested=frozenset({"bob"}),
                requested_at=(("bob", T0 + timedelta(minutes=1)),),
            ),
            ReviewStatus.AWAITING_DISMISSAL,
        ),
        (
            reviews(unresolved=(comment("cat"),)),
            ReviewStatus.COMMENTED,
        ),
        (
            reviews(
                "REVIEW_REQUIRED",
                (opinion("cat", "APPROVED", T0),),
                unresolved=(comment("cat", LATER),),
            ),
            ReviewStatus.COMMENTED,
        ),
    ],
    ids=[
        "approved",
        "approved with no review rules",
        "changes requested",
        "re-requested blocker approved by another user since",
        "unresolved comment",
        "unresolved comment after approval",
    ],
)
def test_review_status(state: Reviews, status: ReviewStatus) -> None:
    assert review_status(state) == status


@pytest.mark.parametrize(
    "state",
    [
        reviews("REVIEW_REQUIRED"),
        reviews("REVIEW_REQUIRED", (opinion("bob", "DISMISSED"),)),
        reviews(
            "APPROVED",
            (opinion("ann", "APPROVED"),),
            requested=frozenset({"ann"}),
        ),
        reviews(
            "CHANGES_REQUESTED",
            (opinion("bob", "CHANGES_REQUESTED"), opinion("ann", "APPROVED", T0)),
            requested=frozenset({"bob"}),
            requested_at=(("bob", T0 + timedelta(minutes=1)),),
        ),
        reviews(
            requested=frozenset({"cat"}),
            unresolved=(comment("cat"),),
        ),
        reviews(
            "REVIEW_REQUIRED",
            (opinion("cat", "APPROVED", LATER),),
            unresolved=(comment("cat", T0),),
        ),
        reviews(
            "REVIEW_REQUIRED",
            (opinion("cat", "DISMISSED", LATER),),
            unresolved=(comment("cat", T0),),
        ),
    ],
    ids=[
        "no reviews",
        "dismissed",
        "re-requested approver",
        "re-requested blocker approved before the request",
        "re-requested commenter",
        "comment cleared by later approval",
        "comment cleared by later dismissal",
    ],
)
def test_open_review_status(state: Reviews) -> None:
    assert review_status(state) == ReviewStatus.OPEN


@pytest.mark.parametrize(
    "state, status",
    [
        (reviews(draft=True), ReviewStatus.DRAFT),
        (
            reviews("APPROVED", (opinion("ann", "APPROVED"),), draft=True),
            ReviewStatus.APPROVED,
        ),
    ],
    ids=["no reviews", "approved"],
)
def test_draft_review_status(state: Reviews, status: ReviewStatus) -> None:
    assert review_status(state) == status


def test_no_pr_has_no_review_status() -> None:
    assert review_status(NO_PR) is None


@pytest.mark.parametrize(
    "result, outcome",
    [
        (
            Result(reviews("APPROVED", (opinion("ann", "APPROVED"),)), TimeoutError()),
            Outcome(
                ReviewStatus.APPROVED,
                "TimeoutError",
                PR_URL,
                has_pr=True,
                tooltip="Approved by ann",
            ),
        ),
        (Result(None, TimeoutError()), Outcome(error="TimeoutError")),
        (Pending.PENDING, Outcome(loading=True)),
        (Result(NO_PR), Outcome(has_pr=False)),
    ],
    ids=[
        "failed load keeps the last status",
        "first load failed",
        "loading",
        "no PR",
    ],
)
def test_review_outcome(
    result: Result[Reviews] | Pending, outcome: Outcome[ReviewStatus]
) -> None:
    assert review_outcome(result) == outcome


@pytest.mark.parametrize(
    "state, tooltip",
    [
        (
            reviews(
                "APPROVED", (opinion("bob", "APPROVED"), opinion("ann", "APPROVED"))
            ),
            "Approved by ann, bob",
        ),
        (
            reviews(opinionated=(opinion("ann", "CHANGES_REQUESTED"),)),
            "Changes requested by ann",
        ),
        (
            reviews(
                "CHANGES_REQUESTED",
                (
                    opinion("ann", "CHANGES_REQUESTED"),
                    opinion("bob", "APPROVED", LATER),
                ),
                requested=frozenset({"ann"}),
                requested_at=(("ann", T0),),
            ),
            "Undismissed blocking review by ann",
        ),
        (
            reviews(unresolved=(comment("cat"), comment("cat"))),
            "2 unresolved threads",
        ),
        (
            reviews(
                requested=frozenset({"bob", "ann"}),
                requested_at=(("ann", T0), ("bob", T0), ("ann", LATER)),
            ),
            "Awaiting ann, bob (2d)",
        ),
        (reviews(), "No reviewers requested"),
        (
            reviews(
                requested=frozenset({"ann"}), requested_at=(("ann", T0),), draft=True
            ),
            "Draft, awaiting ann (2d)",
        ),
        (reviews(draft=True), "Draft, no reviewers requested"),
    ],
    ids=[
        "approved",
        "changes requested",
        "awaiting dismissal",
        "threads from one review",
        "awaiting since the oldest request",
        "no reviewers",
        "draft",
        "draft with no reviewers",
    ],
)
def test_review_tooltip(state: Reviews, tooltip: str) -> None:
    status = review_status(state)
    assert status is not None

    assert review_tooltip(state, status, T0 + timedelta(days=2)) == tooltip


def test_changes_requested_links_to_the_latest_change_request() -> None:
    state = reviews(
        "CHANGES_REQUESTED",
        (
            opinion("bob", "CHANGES_REQUESTED", LATER, url="bob"),
            opinion("dan", "CHANGES_REQUESTED", T0, url="dan"),
        ),
    )

    assert review_outcome(Result(state)).url == "bob"


def test_comments_link_to_the_oldest_review_with_an_unresolved_comment() -> None:
    state = reviews(
        unresolved=(comment("cat", LATER, url="cat"), comment("eve", T0, url="eve"))
    )

    assert review_outcome(Result(state)).url == "eve"


def test_review_without_url_links_to_the_pr() -> None:
    state = reviews(unresolved=(comment("cat"),))

    assert review_outcome(Result(state)).url == PR_URL


@pytest.mark.parametrize(
    "result, interval",
    [
        (Result(None, aiohttp.ClientConnectionError()), RETRY_INTERVAL),
        (Result(None, TimeoutError()), POLL_INTERVAL),
        (Result(NO_PR), POLL_INTERVAL),
    ],
    ids=["connection failure", "timeout", "loaded"],
)
def test_poll_interval(result: Result[Reviews], interval: float) -> None:
    assert poll_interval(result, DISMISSAL_PERIOD) == interval


def test_poll_interval_is_fast_just_after_a_push() -> None:
    assert poll_interval(Result(NO_PR), 0) == FAST_INTERVAL


def page(items: list[Any], *, end: str | None = None, key: str = "nodes") -> Any:
    return {"pageInfo": {"hasNextPage": end is not None, "endCursor": end}, key: items}


def thread(cursor: str, resolved: bool, author: str = "cat") -> dict[str, Any]:
    review = {
        "url": None,
        "state": "COMMENTED",
        "submittedAt": None,
        "author": {"login": author},
    }
    comments = {"nodes": [{"pullRequestReview": review}]}
    return {"cursor": cursor, "node": {"isResolved": resolved, "comments": comments}}


def resolved_threads(count: int) -> list[dict[str, Any]]:
    return [thread(f"t{i}", True) for i in range(1, count + 1)]


class FakeGitHub:
    def __init__(
        self,
        threads: list[dict[str, Any]],
        *,
        pr_id: str = "PR",
        opinionated: Mapping[str | None, Any] = {None: page([])},
    ) -> None:
        self.threads = threads
        self.pr_id = pr_id
        self.opinionated = opinionated
        self.thread_pages: list[tuple[str | None, int]] = []

    def threads_page(self, variables: Mapping[str, Any]) -> dict[str, Any]:
        after, first = variables["threadsAfter"], variables["threadsFirst"]
        self.thread_pages.append((after, first))
        cursors = [edge["cursor"] for edge in self.threads]
        start = cursors.index(after) + 1 if after else 0
        edges = self.threads[start : start + first]
        more = start + first < len(self.threads)
        return {
            "totalCount": len(self.threads),
            **page(edges, end=edges[-1]["cursor"] if more else None, key="edges"),
        }

    async def fetch(self, document: str, variables: Mapping[str, Any]) -> Any:
        if document == REVIEW_THREADS.page_query:
            return {"node": {"reviewThreads": self.threads_page(variables)}}
        if document == OPINIONATED_REVIEWS.page_query:
            after = variables["opinionatedAfter"]
            return {"node": {"latestOpinionatedReviews": self.opinionated[after]}}
        assert document == PR_REVIEWS_QUERY
        pr = {
            "id": self.pr_id,
            "url": PR_URL,
            "reviewDecision": None,
            "isDraft": False,
            "latestOpinionatedReviews": self.opinionated[None],
            "reviewRequests": page([]),
            "timelineItems": page([]),
            "reviewThreads": self.threads_page(variables),
        }
        return {"repository": {"ref": {"associatedPullRequests": {"nodes": [pr]}}}}


async def load(github: FakeGitHub, previous: Reviews | None) -> Reviews:
    return await load_pr_reviews(github.fetch, previous, "o", "n", "refs/heads/b")


async def test_load_reads_every_page() -> None:
    review = {
        "url": "ann",
        "state": "APPROVED",
        "submittedAt": None,
        "author": {"login": "ann"},
    }
    github = FakeGitHub(
        [*resolved_threads(11), thread("t12", False)],
        opinionated={None: page([], end="r1"), "r1": page([review])},
    )

    state = await load(github, None)

    assert state.opinionated == (Review("ann", "APPROVED", None, "ann"),)
    assert state.unresolved == (Review("cat", "COMMENTED", None),)
    assert github.thread_pages == [(None, 10), ("t10", 2)]


async def test_load_resumes_before_the_first_unresolved_thread() -> None:
    github = FakeGitHub([*resolved_threads(2), thread("t3", False)])
    previous = Reviews("PR", threads_cursor="t1", threads_before=1)

    state = await load(github, previous)

    assert github.thread_pages == [("t1", 10)]
    assert (state.threads_cursor, state.threads_before, state.threads_after) == (
        "t2",
        2,
        1,
    )


async def test_first_threads_page_fits_the_threads_of_the_last_load() -> None:
    github = FakeGitHub([thread(f"t{i}", False) for i in range(30)])
    previous = Reviews("PR", threads_after=30)

    await load(github, previous)

    assert github.thread_pages == [(None, 35)]


async def test_load_reads_all_threads_of_a_new_pr() -> None:
    github = FakeGitHub(resolved_threads(3), pr_id="PR2")
    previous = Reviews("PR1", threads_cursor="t1", threads_before=1)

    await load(github, previous)

    assert github.thread_pages == [("t1", 10), (None, 3)]
