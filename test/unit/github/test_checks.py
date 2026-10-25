from typing import Any

import pytest

from git_graph_branch.github.checks import (
    FAST_INTERVAL,
    MEDIUM_INTERVAL,
    SLOW_INTERVAL,
    CheckStatus,
    check_outcome,
    poll_interval,
)
from git_graph_branch.github.common import Outcome
from git_graph_branch.github.loader import Pending, Result
from git_graph_branch.github.remote import Repository

REPOSITORY = Repository("github.com", "o", "n")
NEW_PR_URL = "https://github.com/o/n/pull/new/b"


def response(
    pr_state: str | None,
    *,
    base_has_checks: bool = True,
) -> dict[str, Any]:
    """A response for a branch on a fork, whose default branch has no checks."""
    base_rollup = {"state": "SUCCESS"} if base_has_checks else None
    pr_rollup = {"state": pr_state} if pr_state else None
    return {
        "repository": {
            "defaultBranchRef": {"name": "main"},
            "ref": {
                "associatedPullRequests": {
                    "nodes": [
                        {
                            "baseRepository": {
                                "defaultBranchRef": {
                                    "target": {"statusCheckRollup": base_rollup}
                                }
                            },
                            "commits": {
                                "nodes": [{"commit": {"statusCheckRollup": pr_rollup}}]
                            },
                        }
                    ]
                }
            },
        }
    }


NO_PR: dict[str, Any] = {
    "repository": {
        "defaultBranchRef": {"name": "main"},
        "ref": {"associatedPullRequests": {"nodes": []}},
    }
}


def outcome(
    result: Result[dict[str, Any]] | Pending, branch: str = "b"
) -> Outcome[CheckStatus]:
    return check_outcome(result, REPOSITORY, branch)


@pytest.mark.parametrize(
    "state, status",
    [
        ("FAILURE", CheckStatus.FAILED),
        ("ERROR", CheckStatus.FAILED),
        ("PENDING", CheckStatus.PENDING),
        ("EXPECTED", CheckStatus.PENDING),
        ("SUCCESS", CheckStatus.PASSED),
    ],
)
def test_check_status_from_rollup_state(state: str, status: CheckStatus) -> None:
    assert outcome(Result(response(state))).status == status


def test_no_pr_links_to_pr_creation() -> None:
    assert outcome(Result(NO_PR)) == Outcome(url=NEW_PR_URL, has_pr=False)


def test_default_branch_has_no_pr_creation_link() -> None:
    assert outcome(Result(NO_PR), branch="main") == Outcome(has_pr=False)


@pytest.mark.parametrize(
    "result",
    [{"repository": None}, {"repository": {"ref": None}}],
    ids=["no repository", "no remote branch"],
)
def test_no_pr_creation_link_without_the_remote_branch(
    result: dict[str, Any],
) -> None:
    assert outcome(Result(result)) == Outcome(has_pr=False)


def test_pr_with_no_checks_has_no_status() -> None:
    assert outcome(Result(response(None))) == Outcome(has_pr=True)


def test_failed_load_keeps_the_last_status() -> None:
    result = Result(response("SUCCESS"), TimeoutError())

    assert outcome(result) == Outcome(CheckStatus.PASSED, failed=True, has_pr=True)


def test_first_failed_load_has_no_status() -> None:
    assert outcome(Result(None, TimeoutError())) == Outcome(failed=True)


def test_unknown_rollup_state_is_a_failure() -> None:
    assert outcome(Result(response("NEW_STATE"))) == Outcome(failed=True, has_pr=True)


def test_pending_load_is_loading() -> None:
    assert outcome(Pending.PENDING) == Outcome(loading=True)


@pytest.mark.parametrize(
    "result, age, interval",
    [
        (Result(response("SUCCESS")), 0, FAST_INTERVAL),
        (Result(response("SUCCESS")), 600, SLOW_INTERVAL),
        (Result(response("PENDING")), 600, MEDIUM_INTERVAL),
        (Result(NO_PR), 600, SLOW_INTERVAL),
        (Result(response(None, base_has_checks=False)), 0, SLOW_INTERVAL),
        (Result(response("SUCCESS"), TimeoutError()), 0, MEDIUM_INTERVAL),
    ],
    ids=[
        "just pushed",
        "final",
        "pending",
        "no PR",
        "base repository has no checks",
        "failed load",
    ],
)
def test_poll_interval(
    result: Result[dict[str, Any]], age: float, interval: float
) -> None:
    assert poll_interval(result, age) == interval
