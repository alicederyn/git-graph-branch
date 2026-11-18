from collections.abc import Iterator

import pytest

from git_graph_branch.github import store
from git_graph_branch.github.store import assumes_no_pr, forget_push, read_branches
from git_graph_branch.nix.fact import (
    Fact,
    release_moot_facts,
    report_calculation,
    session,
)

X = ("origin", "x")


@pytest.fixture(autouse=True)
def watching() -> Iterator[None]:
    with session(None):
        yield


type Branches = tuple[dict[tuple[str, str], str], dict[str, str]]
"""The commits of the remote-tracking branches and of the local branches."""

NONE: Branches = ({}, {})
LOCAL: Branches = ({}, {"x": "c1"})
PUSHED: Branches = ({X: "c1"}, {"x": "c1"})


def reports(*calculations: Branches | None) -> None:
    """Read the branches into the store in each report, as the watch loop does:
    each change nixes the last report, and moot facts are released when a report
    is complete. None is a report that does not read the store."""
    report: Fact | None = None
    for branches in calculations:
        if report is not None:
            report.nix()
        with report_calculation() as report:
            if branches is not None:
                # New objects for each report, as the cached lists make
                remote, local = dict(branches[0]), dict(branches[1])
                for _ in range(2):
                    read_branches(remote, local)
        release_moot_facts()


def just_pushed() -> bool:
    return assumes_no_pr(X, "checks", pending=True)


def test_push_of_an_existing_local_branch_is_just_pushed() -> None:
    reports(LOCAL, PUSHED)

    assert just_pushed()


def test_push_of_a_local_branch_made_after_the_first_read_is_just_pushed() -> None:
    reports(NONE, LOCAL, PUSHED)

    assert just_pushed()


def test_branch_that_existed_at_the_first_read_is_not_just_pushed() -> None:
    reports(PUSHED, PUSHED)

    assert not just_pushed()


def test_fetch_and_checkout_together_is_not_just_pushed() -> None:
    reports(NONE, PUSHED)

    assert not just_pushed()


def test_new_remote_branch_at_another_commit_is_not_just_pushed() -> None:
    reports(LOCAL, ({X: "c2"}, {"x": "c1"}))

    assert not just_pushed()


def test_later_commits_keep_the_branch_just_pushed() -> None:
    reports(LOCAL, PUSHED, ({X: "c2"}, {"x": "c3"}))

    assert just_pushed()


@pytest.mark.parametrize(
    "after", [LOCAL, ({X: "c1"}, {})], ids=["remote deleted", "local deleted"]
)
def test_deleted_branch_is_no_longer_just_pushed(after: Branches) -> None:
    reports(LOCAL, PUSHED, after)

    assert not just_pushed()


def test_store_is_dropped_when_a_report_does_not_read_it() -> None:
    reports(LOCAL, None)

    assert store.store is None


def test_a_load_assumes_no_pr_until_it_gives_a_result() -> None:
    reports(LOCAL, PUSHED)

    assert assumes_no_pr(X, "checks", pending=True)
    assert not assumes_no_pr(X, "checks", pending=False)
    assert not assumes_no_pr(X, "checks", pending=True)
    assert assumes_no_pr(X, "reviews", pending=True)


def test_found_pr_ends_the_assumption() -> None:
    reports(LOCAL, PUSHED)

    forget_push(X)

    assert not just_pushed()


def test_push_of_a_new_local_commit_is_just_pushed() -> None:
    reports(({}, {"x": "c0"}), PUSHED)

    assert just_pushed()


def test_new_remote_branch_at_an_old_local_commit_is_not_just_pushed() -> None:
    reports(({}, {"x": "c0"}), ({X: "c0"}, {"x": "c1"}))

    assert not just_pushed()
