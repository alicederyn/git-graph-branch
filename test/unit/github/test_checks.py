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
from git_graph_branch.github.common import Outcome, combine
from git_graph_branch.github.loader import Pending, Result


def response(pr_state: str | None, *, base_has_checks: bool = True) -> dict[str, Any]:
    """A response for a branch on a fork, whose default branch has no checks."""
    base_rollup = {"state": "SUCCESS"} if base_has_checks else None
    pr_rollup = {"state": pr_state} if pr_state else None
    return {
        "repository": {
            "defaultBranchRef": {"target": {"statusCheckRollup": None}},
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
    "repository": {"ref": {"associatedPullRequests": {"nodes": []}}}
}


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
    assert check_outcome(Result(response(state))) == Outcome(status)


@pytest.mark.parametrize(
    "result",
    [NO_PR, response(None), {"repository": None}, {"repository": {"ref": None}}],
    ids=["no PR", "no checks", "no repository", "no remote branch"],
)
def test_no_check_status(result: dict[str, Any]) -> None:
    assert check_outcome(Result(result)) == Outcome()


def test_failed_load_keeps_the_last_status() -> None:
    result = Result(response("SUCCESS"), TimeoutError())

    assert check_outcome(result) == Outcome(CheckStatus.PASSED, failed=True)


def test_first_failed_load_has_no_status() -> None:
    assert check_outcome(Result(None, TimeoutError())) == Outcome(failed=True)


def test_unknown_rollup_state_is_a_failure() -> None:
    assert check_outcome(Result(response("NEW_STATE"))) == Outcome(failed=True)


def test_pending_load_is_loading() -> None:
    assert check_outcome(Pending.PENDING) == Outcome(CheckStatus.LOADING)


@pytest.mark.parametrize(
    "statuses, combined",
    [
        ([CheckStatus.PASSED, CheckStatus.FAILED], CheckStatus.FAILED),
        ([CheckStatus.PASSED, CheckStatus.PENDING], CheckStatus.PENDING),
        ([CheckStatus.FAILED, CheckStatus.LOADING], CheckStatus.FAILED),
        ([CheckStatus.PENDING, CheckStatus.LOADING], CheckStatus.LOADING),
        ([None, CheckStatus.PASSED], CheckStatus.PASSED),
        ([None, None], None),
        ([], None),
    ],
)
def test_combine(
    statuses: list[CheckStatus | None], combined: CheckStatus | None
) -> None:
    assert combine(statuses) == combined


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
