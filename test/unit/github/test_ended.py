from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from git_graph_branch.github.common import Outcome
from git_graph_branch.github.ended import (
    CANDIDATES_PAGE_QUERY,
    COMMITS_PAGE_QUERY,
    ENDED_PRS_QUERY,
    EndedPr,
    EndedState,
    agreeing,
    ended_outcome,
    load_ended_prs,
)
from git_graph_branch.graphql.loader import Pending, Result

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
LOCAL = "local"
OWN = "me/n"
PARENT = "them/n"


def iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def commit(oid: str, at: datetime) -> dict[str, Any]:
    return {"commit": {"oid": oid, "committedDate": iso(at)}}


def pr(
    number: int,
    commits: list[dict[str, Any]],
    *,
    state: str = "MERGED",
    updated: datetime = T0 + timedelta(hours=1),
    head_repository: str = OWN,
) -> dict[str, Any]:
    """A PR, with commits oldest first."""
    return {
        "id": f"PR{number}",
        "state": state,
        "url": f"https://github.com/{PARENT}/pull/{number}",
        "updatedAt": iso(updated),
        "headRefOid": commits[-1]["commit"]["oid"],
        "headRepository": {"nameWithOwner": head_repository},
        "all_commits": commits,
    }


class FakeGitHub:
    def __init__(
        self, own: list[dict[str, Any]], parent: list[dict[str, Any]] | None = None
    ) -> None:
        self.prs = {OWN: own, PARENT: parent or []}
        self.has_parent = parent is not None
        self.documents: list[str] = []

    def commits_page(self, pr: dict[str, Any], last: int, before: str | None) -> Any:
        commits = pr["all_commits"]
        end = int(before) if before else len(commits)
        start = max(0, end - last)
        return {
            "pageInfo": {"hasPreviousPage": start > 0, "startCursor": str(start)},
            "nodes": commits[start:end],
        }

    def candidates_page(self, base: str, variables: Mapping[str, Any]) -> Any:
        prs = self.prs[base]
        start = int(variables["after"] or 0)
        end = start + variables["first"]
        nodes = [
            {
                **{k: v for k, v in p.items() if k != "all_commits"},
                "commits": self.commits_page(p, variables["commits"], None),
            }
            for p in prs[start:end]
        ]
        return {
            "pageInfo": {"hasNextPage": end < len(prs), "endCursor": str(end)},
            "nodes": nodes,
        }

    async def fetch(self, document: str, variables: Mapping[str, Any]) -> Any:
        self.documents.append(document)
        if document == COMMITS_PAGE_QUERY:
            p = next(
                p
                for prs in self.prs.values()
                for p in prs
                if p["id"] == variables["pr"]
            )
            page = self.commits_page(p, variables["last"], variables["before"])
            return {"node": {"commits": page}}
        if document == CANDIDATES_PAGE_QUERY:
            base = f"{variables['owner']}/{variables['name']}"
            return {
                "repository": {"pullRequests": self.candidates_page(base, variables)}
            }
        assert document == ENDED_PRS_QUERY
        parent = (
            {
                "owner": {"login": "them"},
                "name": "n",
                "pullRequests": self.candidates_page(PARENT, variables),
            }
            if self.has_parent
            else None
        )
        return {
            "repository": {
                "nameWithOwner": OWN,
                "pullRequests": self.candidates_page(OWN, variables),
                "parent": parent,
            }
        }


async def load(github: FakeGitHub) -> tuple[EndedPr, ...]:
    return await load_ended_prs(
        github.fetch, None, (LOCAL, int(T0.timestamp())), "me", "n", "b"
    )


def merged(number: int, head: str) -> EndedPr:
    return EndedPr(
        EndedState.MERGED, f"https://github.com/{PARENT}/pull/{number}", head
    )


async def test_merged_pr_with_the_local_commit_as_head() -> None:
    github = FakeGitHub([pr(1, [commit(LOCAL, T0)])])

    assert await load(github) == (merged(1, LOCAL),)


async def test_closed_pr_from_a_fork_is_in_the_parent() -> None:
    github = FakeGitHub([], [pr(1, [commit(LOCAL, T0)], state="CLOSED")])

    assert [p.state for p in await load(github)] == [EndedState.CLOSED]


async def test_commit_walk_reads_back_to_the_local_commit() -> None:
    later = [commit(f"c{i}", T0 + timedelta(minutes=i)) for i in range(1, 15)]
    github = FakeGitHub([pr(1, [commit(LOCAL, T0), *later])])

    assert await load(github) == (merged(1, "c14"),)
    assert github.documents.count(COMMITS_PAGE_QUERY) == 1


async def test_commit_walk_stops_at_an_older_commit() -> None:
    older = [commit(f"c{i}", T0 - timedelta(hours=i)) for i in range(20, 0, -1)]
    github = FakeGitHub([pr(1, [commit(LOCAL, T0 - timedelta(days=1)), *older])])

    assert await load(github) == ()
    assert COMMITS_PAGE_QUERY not in github.documents


async def test_commit_walk_allows_for_clock_skew() -> None:
    skewed = commit("c1", T0 - timedelta(seconds=30))
    github = FakeGitHub([pr(1, [commit(LOCAL, T0), skewed])])

    assert await load(github) == (merged(1, "c1"),)


async def test_pr_from_another_fork_is_not_the_branch_pr() -> None:
    other = pr(1, [commit(LOCAL, T0)], head_repository="other/n")

    assert await load(FakeGitHub([], [other])) == ()


async def test_candidates_stop_at_a_pr_updated_before_the_local_commit() -> None:
    recent = [pr(i, [commit(f"c{i}", T0)]) for i in range(1, 6)]
    old = pr(6, [commit(LOCAL, T0)], updated=T0 - timedelta(days=1))
    github = FakeGitHub([*recent, old])

    assert await load(github) == ()
    assert CANDIDATES_PAGE_QUERY in github.documents


async def test_most_recently_updated_pr_comes_first() -> None:
    older = pr(1, [commit(LOCAL, T0)], updated=T0 + timedelta(hours=1))
    newer = pr(2, [commit(LOCAL, T0)], updated=T0 + timedelta(hours=2))

    assert await load(FakeGitHub([older], [newer])) == (
        merged(2, LOCAL),
        merged(1, LOCAL),
    )


def test_ended_pr_shows_if_the_remote_branch_is_its_head() -> None:
    result = Result((merged(1, "head"),))

    assert ended_outcome(result, "head").status == EndedState.MERGED


def test_ended_pr_shows_if_the_remote_branch_is_deleted() -> None:
    result = Result((merged(1, "head"),))

    assert ended_outcome(result, None) == Outcome(
        EndedState.MERGED, url=merged(1, "head").url, tooltip="PR merged"
    )


def test_ended_pr_does_not_show_after_a_new_push() -> None:
    result = Result((merged(1, "head"),))

    assert ended_outcome(result, "new push") == Outcome()


def test_pending_ended_pr_is_loading() -> None:
    assert ended_outcome(Pending.PENDING, None) == Outcome(loading=True)


def test_first_push_has_no_ended_pr_before_it_loads() -> None:
    assert agreeing(Pending.PENDING, (LOCAL, 0), True) == Result((), None, (LOCAL, 0))


def test_failed_first_load_after_a_first_push_shows_the_error() -> None:
    result: Result[tuple[EndedPr, ...]] = Result(None, TimeoutError())

    assert agreeing(result, (LOCAL, 0), True) is result
