from typing import Any

import pytest

from git_graph_branch.github.checks import (
    FAST_INTERVAL,
    MEDIUM_INTERVAL,
    SLOW_INTERVAL,
    CheckStatus,
    check_status,
    combine,
    poll_interval,
)
from git_graph_branch.github.loader import Pending


def response(pr_state: str | None, *, repo_has_checks: bool = True) -> dict[str, Any]:
    default_rollup = {"state": "SUCCESS"} if repo_has_checks else None
    pr_rollup = {"state": pr_state} if pr_state else None
    return {
        "repository": {
            "defaultBranchRef": {"target": {"statusCheckRollup": default_rollup}},
            "ref": {
                "associatedPullRequests": {
                    "nodes": [
                        {
                            "commits": {
                                "nodes": [{"commit": {"statusCheckRollup": pr_rollup}}]
                            }
                        }
                    ]
                }
            },
        }
    }


NO_PR: dict[str, Any] = {
    "repository": {
        "defaultBranchRef": {"target": {"statusCheckRollup": {"state": "SUCCESS"}}},
        "ref": {"associatedPullRequests": {"nodes": []}},
    }
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
    assert check_status(response(state)) == status


@pytest.mark.parametrize(
    "result",
    [NO_PR, response(None), {"repository": None}, {"repository": {"ref": None}}],
    ids=["no PR", "no checks", "no repository", "no remote branch"],
)
def test_no_check_status(result: dict[str, Any]) -> None:
    assert check_status(result) is None


def test_failed_load_is_unknown() -> None:
    assert check_status(TimeoutError()) == CheckStatus.UNKNOWN


def test_pending_load_is_loading() -> None:
    assert check_status(Pending.PENDING) == CheckStatus.LOADING


@pytest.mark.parametrize(
    "statuses, combined",
    [
        ([CheckStatus.PASSED, CheckStatus.FAILED], CheckStatus.FAILED),
        ([CheckStatus.FAILED, CheckStatus.UNKNOWN], CheckStatus.FAILED),
        ([CheckStatus.PENDING, CheckStatus.UNKNOWN], CheckStatus.UNKNOWN),
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
        (response("SUCCESS"), 0, FAST_INTERVAL),
        (response("SUCCESS"), 600, SLOW_INTERVAL),
        (response("PENDING"), 600, MEDIUM_INTERVAL),
        (NO_PR, 600, SLOW_INTERVAL),
        (response(None, repo_has_checks=False), 0, SLOW_INTERVAL),
        (TimeoutError(), 0, MEDIUM_INTERVAL),
    ],
    ids=[
        "just pushed",
        "final",
        "pending",
        "no PR",
        "repository has no checks",
        "failed load",
    ],
)
def test_poll_interval(result: Any, age: float, interval: float) -> None:
    assert poll_interval(result, age) == interval
