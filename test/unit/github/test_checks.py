from typing import Any
from unittest.mock import AsyncMock

import pytest

from git_graph_branch.github.checks import (
    FAST_INTERVAL,
    MEDIUM_INTERVAL,
    NO_REMOTE_TRACKING_BRANCH,
    SLOW_INTERVAL,
    CheckStatus,
    agreeing,
    check_outcome,
    load_pr_checks,
    poll_interval,
)
from git_graph_branch.github.common import Outcome
from git_graph_branch.github.remote import Repository
from git_graph_branch.graphql.loader import Pending, Result

REPOSITORY = Repository("github.com", "o", "n")
NEW_PR_URL = "https://github.com/o/n/pull/new/b"
LOCAL_OID = "local"


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
                "target": {"oid": LOCAL_OID},
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
                },
            },
        }
    }


NO_PR: dict[str, Any] = {
    "repository": {
        "defaultBranchRef": {"name": "main"},
        "ref": {"target": {"oid": LOCAL_OID}, "associatedPullRequests": {"nodes": []}},
    }
}


def outcome(
    result: Result[dict[str, Any]] | Pending, branch: str = "b"
) -> Outcome[CheckStatus]:
    return check_outcome(result, REPOSITORY, branch, "origin", LOCAL_OID)


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
    assert outcome(Result(NO_PR)) == Outcome(
        url=NEW_PR_URL, has_pr=False, remote_oid=LOCAL_OID
    )


def test_default_branch_has_no_pr_creation_link() -> None:
    assert outcome(Result(NO_PR), branch="main") == Outcome(
        has_pr=False, remote_oid=LOCAL_OID
    )


def test_no_pr_creation_link_without_the_repository() -> None:
    assert outcome(Result({"repository": None})) == Outcome(has_pr=False)


def test_deleted_remote_branch_has_no_pr_creation_link() -> None:
    assert outcome(Result({"repository": {"ref": None}})) == Outcome(
        has_pr=False, remote_reason="origin: deleted on remote"
    )


def test_remote_branch_changed_on_github() -> None:
    data = response("SUCCESS")
    data["repository"]["ref"]["target"]["oid"] = "pushed elsewhere"

    assert outcome(Result(data)) == Outcome(
        CheckStatus.PASSED,
        has_pr=True,
        remote_oid="pushed elsewhere",
        remote_reason="origin: changed on remote",
    )


def test_pr_with_no_checks_has_no_status() -> None:
    assert outcome(Result(response(None))) == Outcome(has_pr=True, remote_oid=LOCAL_OID)


def test_failed_load_keeps_the_last_status() -> None:
    result = Result(response("SUCCESS"), TimeoutError())

    assert outcome(result) == Outcome(
        CheckStatus.PASSED, "TimeoutError", has_pr=True, remote_oid=LOCAL_OID
    )


def test_first_failed_load_has_no_status() -> None:
    assert outcome(Result(None, TimeoutError())) == Outcome(error="TimeoutError")


def test_unknown_rollup_state_is_a_failure() -> None:
    assert outcome(Result(response("NEW_STATE"))) == Outcome(
        error="Unknown check state NEW_STATE", has_pr=True, remote_oid=LOCAL_OID
    )


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


def test_push_moves_the_remote_branch() -> None:
    data = response("SUCCESS")
    data["repository"]["ref"]["target"]["oid"] = "before push"
    pushed = agreeing(Result(data, None, "before push"), LOCAL_OID)

    assert outcome(pushed) == Outcome(
        CheckStatus.PASSED, has_pr=True, remote_oid=LOCAL_OID
    )


def test_push_after_deletion_makes_the_remote_branch_with_no_pr() -> None:
    pushed = agreeing(Result({"repository": {"ref": None}}, None, "old"), LOCAL_OID)

    assert outcome(pushed) == Outcome(
        url=NEW_PR_URL, has_pr=False, remote_oid=LOCAL_OID
    )


def test_first_push_makes_the_remote_branch_with_no_pr() -> None:
    pushed = agreeing(Result(NO_REMOTE_TRACKING_BRANCH), LOCAL_OID)

    assert outcome(pushed) == Outcome(
        url=NEW_PR_URL, has_pr=False, remote_oid=LOCAL_OID
    )


def test_result_for_the_current_commit_is_not_changed() -> None:
    result = Result(response("SUCCESS"), None, LOCAL_OID)

    assert agreeing(result, LOCAL_OID) is result


def test_no_remote_tracking_branch_has_no_pr() -> None:
    result = agreeing(Result(response("SUCCESS"), None, LOCAL_OID), None)

    assert check_outcome(result, REPOSITORY, "b", "origin", None) == Outcome(
        has_pr=False
    )


async def test_no_remote_tracking_branch_sends_no_request() -> None:
    fetch = AsyncMock()

    state = await load_pr_checks(fetch, None, None, "o", "n", "refs/heads/b")

    assert state == NO_REMOTE_TRACKING_BRANCH
    fetch.assert_not_called()
